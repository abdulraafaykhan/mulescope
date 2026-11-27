"""One decorator that records every node: diagnostics, audit and live progress.

``@node("name", agent="code")`` wraps an async node function. It writes a
``node_executions`` row (start, end, latency, tokens, retries, status,
fallback flag and reason), appends an audit event to the case hash chain and publishes
``{node, status, message, tokens}`` through LangGraph's stream writer, so the
node bodies stay free of logging code. It also binds the node scope, so every
LLM call attempt made inside the node is logged with its case, run and node.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.errors import GraphInterrupt

from backend.app.core.logging import bind_run_context, get_logger
from backend.app.core.node_scope import NodeScope, bind_node_scope
from backend.app.graph.deps import deps_of
from backend.app.graph.state import CaseState

NodeFn = Callable[[CaseState, RunnableConfig], Awaitable[dict[str, Any]]]
_logger = get_logger(__name__)

# Agent nodes report tokens and the fallback flag in their update under this key.
META_KEY = "_node_meta"


def _writer() -> Callable[[Any], None]:
    try:
        return get_stream_writer()
    except Exception:  # noqa: BLE001 - outside a streaming run there is no writer
        return lambda _event: None


def node(name: str, agent: str = "code") -> Callable[[NodeFn], NodeFn]:
    """Instrument a graph node.

    Args:
        name: Node name, as registered in the graph.
        agent: ``code``, ``profiler``, ``flow``, ``narrative`` or ``critic``
            (drives the colour in the UI).
    """

    def deco(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        async def wrapper(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
            deps = deps_of(config)
            case_id, run_id = state.get("case_id"), state.get("run_id")
            write = _writer()
            started = deps.clock.now()
            t0 = time.perf_counter()
            oid = await deps.node_execs.insert({
                "run_id": run_id, "case_id": case_id, "node": name, "agent": agent, "status": "running",
                "started_at": started, "created_at": started, "latency_ms": None, "tokens_in": 0, "tokens_out": 0, "retries": 0, "fallback_used": False, "fallback_reason": None,
            })
            write({"type": "node", "node": name, "agent": agent, "status": "running", "message": f"{name} started", "tokens": 0})
            scope = NodeScope(case_id=case_id, run_id=run_id, node=name, agent=agent, node_exec_id=str(oid))
            with bind_run_context(case_id, run_id), bind_node_scope(scope):
                try:
                    update = await fn(state, config)
                except GraphInterrupt:
                    latency = int((time.perf_counter() - t0) * 1000)
                    await deps.node_execs.update(oid, {"status": "waiting", "latency_ms": latency, "ended_at": deps.clock.now()})
                    write({"type": "node", "node": name, "agent": agent, "status": "waiting", "message": "waiting for analyst decision", "tokens": 0})
                    raise
                except Exception as exc:
                    latency = int((time.perf_counter() - t0) * 1000)
                    await deps.node_execs.update(oid, {"status": "error", "latency_ms": latency, "error": f"{type(exc).__name__}: {exc}"[:500], "ended_at": deps.clock.now()})
                    await deps.audit.append(ts=deps.clock.now(), actor={"type": "agent" if agent != "code" else "system", "id": name}, event=f"node.{name}.failed", entity={"type": "case_run", "id": run_id or ""}, case_id=case_id, run_id=run_id, payload={"error": type(exc).__name__})
                    write({"type": "node", "node": name, "agent": agent, "status": "error", "message": str(exc)[:200], "tokens": 0})
                    _logger.exception("node failed", extra={"node": name})
                    raise
            meta = update.pop(META_KEY, {}) if isinstance(update, dict) else {}
            latency = int((time.perf_counter() - t0) * 1000)
            status = "fallback" if meta.get("fallback_used") else "done"
            reason = meta.get("fallback_reason")
            tokens = int(meta.get("tokens_in", 0)) + int(meta.get("tokens_out", 0))
            await deps.node_execs.update(oid, {
                "status": status, "latency_ms": latency, "ended_at": deps.clock.now(),
                "tokens_in": int(meta.get("tokens_in", 0)), "tokens_out": int(meta.get("tokens_out", 0)), "retries": int(meta.get("retries", 0)),
                "fallback_used": bool(meta.get("fallback_used", False)), "fallback_reason": reason, "prompt_version": meta.get("prompt_version"), "model": meta.get("model"),
                "output_summary": meta.get("summary"), "tool_calls": meta.get("tool_calls", []), "cache_hit": bool(meta.get("cache_hit", False)),
            })
            await deps.audit.append(
                ts=deps.clock.now(), actor={"type": "agent" if agent != "code" else "system", "id": name}, event=f"node.{name}.completed",
                entity={"type": "case_run", "id": run_id or ""}, case_id=case_id, run_id=run_id,
                payload={"latency_ms": latency, "status": status, "summary": meta.get("summary"), **({"fallback_reason": reason} if reason else {})},
            )
            write({"type": "node", "node": name, "agent": agent, "status": status, "message": meta.get("summary") or f"{name} done", "tokens": tokens, "latency_ms": latency, "fallback_reason": reason})
            return update

        return wrapper

    return deco
