"""Starts, streams and resumes graph runs for cases.

``start_run`` creates the ``case_runs`` row and drives the compiled graph in a
background task, forwarding ``astream(stream_mode=["updates", "custom"])``
events to the run's event bus. The graph pauses at ``analyst_gate``;
``decide`` resumes it with ``Command(resume=decision)``. ``thread_id =
run_id``, so a run survives an API restart through the Mongo checkpointer.

Idempotency: a case with a run that is still running or awaiting a decision
reuses that run instead of starting a duplicate.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langgraph.types import Command

from backend.app.core.errors import NotFound, PolicyViolation
from backend.app.core.logging import get_logger
from backend.app.domain.enums import Disposition
from backend.app.graph.deps import GraphDeps
from backend.app.services.event_bus import RunEventBus

_logger = get_logger(__name__)
ACTIVE = {"running", "awaiting_decision"}
DECISIONS = {"approve", "edit", "override", "request_more", "reject"}


class CaseRunner:
    """Owns background graph executions."""

    def __init__(self, graph: Any, deps: GraphDeps, bus: RunEventBus, graph_version: str, llm_mode: str, dataset_seed: int | None) -> None:
        self._graph, self._deps, self._bus = graph, deps, bus
        self._graph_version, self._llm_mode, self._seed = graph_version, llm_mode, dataset_seed
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def _config(self, run_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": run_id, "deps": self._deps}, "recursion_limit": 60}

    async def start_run(self, case_id: str) -> dict[str, Any]:
        """Start (or reuse) a run for ``case_id``; returns the run document."""
        deps = self._deps
        case = await deps.cases.get(case_id)
        if case is None:
            raise NotFound(f"case {case_id} not found", detail={"case_id": case_id})
        current = await deps.runs.latest_for_case(case_id)
        if current and current.get("status") in ACTIVE and current.get("graph_version") == self._graph_version:
            return current
        now = deps.clock.now()
        run_id = (await deps.counters.next_ids("runs", "RUN-", 1, now, width=5))[0]
        doc = {
            "_id": run_id, "case_id": case_id, "thread_id": run_id, "graph_version": self._graph_version,
            "prompt_versions": {"profiler": "template-1", "flow_analyst": "template-1", "narrative": "template-1", "critic": "template-1"},
            "models": {"profiler": "template", "flow_analyst": "template", "narrative": "template", "critic": "template"} if self._llm_mode == "fallback" else {},
            "dataset_seed": self._seed, "llm_mode": self._llm_mode, "status": "running", "started_at": now, "ended_at": None,
            "totals": {"tokens": 0, "latency_ms": 0, "retries": 0}, "created_at": now,
        }
        await deps.runs.insert(doc)
        await deps.cases.update(case_id, {"current_run_id": run_id}, now)
        await deps.audit.append(ts=now, actor={"type": "system", "id": "case_runner"}, event="run.started", entity={"type": "case_run", "id": run_id}, case_id=case_id, run_id=run_id, payload={"graph_version": self._graph_version, "llm_mode": self._llm_mode})
        state = {"case_id": case_id, "run_id": run_id, "llm_mode": self._llm_mode, "facts": [], "errors": []}
        self._spawn(run_id, state)
        return {**doc, "id": run_id}

    async def decide(self, case_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        """Resume the paused run of ``case_id`` with an analyst decision."""
        kind = decision.get("decision")
        if kind not in DECISIONS:
            raise PolicyViolation(f"unknown decision {kind!r}", detail={"allowed": sorted(DECISIONS)})
        if kind == "override":
            if not (decision.get("reason") or "").strip():
                raise PolicyViolation("an override of the policy requires a reason")
            if decision.get("override_disposition") not in {d.value for d in Disposition}:
                raise PolicyViolation("override_disposition must be close, escalate or str_draft")
        if kind == "reject" and not (decision.get("reason") or "").strip():
            raise PolicyViolation("rejecting the recommendation requires a reason")
        run = await self._deps.runs.latest_for_case(case_id)
        if run is None or run.get("status") != "awaiting_decision":
            raise PolicyViolation("this case has no run waiting for a decision", detail={"case_id": case_id})
        await self._deps.runs.update(run["id"], {"status": "running"}, self._deps.clock.now())
        self._spawn(run["id"], Command(resume=decision))
        return {"run_id": run["id"], "status": "running"}

    def _spawn(self, run_id: str, payload: Any) -> None:
        task = asyncio.create_task(self._drive(run_id, payload))
        self._tasks[run_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(run_id, None))

    async def run_to_interrupt(self, run_id: str, payload: Any) -> None:
        """Drive the graph inline (scripts and smoke tests)."""
        await self._drive(run_id, payload)

    def is_driving(self, run_id: str) -> bool:
        """True when this process has a live task driving ``run_id``."""
        return run_id in self._tasks

    async def wait(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task:
            await task

    async def _drive(self, run_id: str, payload: Any) -> None:
        deps = self._deps
        try:
            async for mode, chunk in self._graph.astream(payload, self._config(run_id), stream_mode=["updates", "custom"]):
                if mode == "custom":
                    self._bus.publish(run_id, chunk)
                elif mode == "updates" and "__interrupt__" in chunk:
                    interrupt_payload = chunk["__interrupt__"][0].value
                    await deps.runs.update(run_id, {"status": "awaiting_decision"}, deps.clock.now())
                    self._bus.publish(run_id, {"type": "interrupt", "node": "analyst_gate", "status": "waiting", "payload": interrupt_payload})
            run = await deps.runs.get(run_id)
            if run and run.get("status") == "completed":
                self._bus.publish(run_id, {"type": "run_completed", "status": "completed", "final_disposition": run.get("final_disposition")})
        except Exception as exc:
            _logger.exception("run failed", extra={"run_id": run_id})
            await deps.runs.update(run_id, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]}, deps.clock.now())
            self._bus.publish(run_id, {"type": "run_failed", "status": "failed", "message": f"{type(exc).__name__}: {exc}"[:300]})
