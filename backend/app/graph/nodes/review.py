"""Review nodes: analyst_gate (interrupt), apply_decision, execute_actions, finalize.

Only a human can override the policy, and an override needs a reason; the
API validates that before resuming the graph. Execution is mocked: actions are
marked executed with a result describing what the mock tool did.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from backend.app.domain.enums import CaseStatus, Disposition
from backend.app.domain.policy.disposition import PolicyResult
from backend.app.graph.deps import deps_of
from backend.app.graph.instrument import META_KEY, node
from backend.app.graph.nodes.decide import _jsonable, _persist_actions, with_current_evidence
from backend.app.graph.state import CaseState

STATUS_BY_DISPOSITION = {
    Disposition.CLOSE.value: CaseStatus.CLOSED.value,
    Disposition.ESCALATE.value: CaseStatus.ESCALATED.value,
    Disposition.STR_DRAFT.value: CaseStatus.STR_DRAFTED.value,
}
EXECUTABLE = {"proposed", "approved"}


@node("analyst_gate")
async def analyst_gate(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    await deps.cases.update(state["case_id"], {"status": CaseStatus.AWAITING_DECISION.value}, deps.clock.now())
    package = {
        "case_id": state["case_id"], "run_id": state["run_id"], "disposition": state["policy"]["disposition"], "score": state["policy"]["score"],
        "report_id": state["report"]["id"], "critic": state.get("critic_result"), "actions": [a["id"] for a in state.get("proposed_actions", [])],
    }
    decision: dict[str, Any] = interrupt(package)
    return {"analyst_decision": decision, META_KEY: {"summary": f"analyst decision: {decision.get('decision')}"}}


@node("apply_decision")
async def apply_decision(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    d = state["analyst_decision"]
    kind = d["decision"]
    policy_disp = state["policy"]["disposition"]
    final = d.get("override_disposition") if kind == "override" else (policy_disp if kind in ("approve", "edit") else None)
    now = deps.clock.now()
    did = (await deps.counters.next_ids("decisions", "DEC-", 1, now, width=5))[0]
    await deps.decisions.insert({
        "_id": did, "case_id": state["case_id"], "run_id": state["run_id"], "user_id": d.get("user_id", "analyst-1"), "role": d.get("role", "analyst"),
        "decision": kind, "policy_disposition": policy_disp, "final_disposition": final, "override_reason": d.get("reason"), "edits": d.get("edits") or {}, "created_at": now,
    })
    await deps.audit.append(ts=now, actor={"type": "analyst", "id": d.get("user_id", "analyst-1")}, event=f"decision.{kind}", entity={"type": "case", "id": state["case_id"]}, case_id=state["case_id"], run_id=state["run_id"],
                            payload={"policy_disposition": policy_disp, "final_disposition": final, "reason": d.get("reason")})
    if kind == "edit" and d.get("edits"):
        version = await deps.reports.next_version(state["case_id"])
        rid = (await deps.counters.next_ids("reports", "RPT-", 1, now, width=5))[0]
        base = {k: state["report"].get(k) for k in ("summary_md", "str_narrative_md", "customer_query_md", "citations", "disposition_stated")}
        await deps.reports.insert({"_id": rid, "case_id": state["case_id"], "run_id": state["run_id"], "version": version, **base, **d["edits"], "critic": state.get("critic_result"), "status": "edited", "created_at": now})
    loops = dict(state.get("loop_counts", {}))
    if kind == "request_more":
        loops["request_more"] = loops.get("request_more", 0) + 1
    return {"final_disposition": final, "loop_counts": loops, "gaps": ["analyst requested more evidence"] if kind == "request_more" else [], META_KEY: {"summary": f"{kind} -> {final or 'no disposition'}"}}


@node("execute_actions")
async def execute_actions(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    d = state["analyst_decision"]
    user = d.get("user_id", "analyst-1")
    now = deps.clock.now()
    actions = await deps.actions.for_case(state["case_id"])
    if d["decision"] == "override" and state.get("final_disposition") != state["policy"]["disposition"]:
        for a in actions:
            if a["status"] in EXECUTABLE:
                await deps.actions.update(a["id"], {"status": "cancelled"}, {"ts": now, "status": "cancelled", "by": user, "reason": "policy overridden"}, now)
        overridden = PolicyResult(**{**state["policy"], "disposition": state["final_disposition"]})
        await _persist_actions(deps, state, overridden)
        actions = await deps.actions.for_case(state["case_id"])
    executed = 0
    for a in actions:
        if a["status"] not in EXECUTABLE:
            continue
        result = {"mock_tool": a["mock_tool"], "ok": True, "message": f"{a['mock_tool']} applied to {a['target']} (mock)"}
        await deps.actions.update(a["id"], {"status": "executed", "approved_by": user if a["requires_approval"] else None, "executed_at": now, "result": result}, {"ts": now, "status": "executed", "by": user}, now)
        await deps.audit.append(ts=now, actor={"type": "system", "id": "execute_actions"}, event="action.executed", entity={"type": "action", "id": a["id"]}, case_id=state["case_id"], run_id=state["run_id"], payload={"type": a["type"], "target": a["target"]})
        executed += 1
    refreshed = await deps.actions.for_case(state["case_id"])
    return {"proposed_actions": _jsonable(with_current_evidence(refreshed, state)), META_KEY: {"summary": f"{executed} actions executed (mock)"}}


@node("finalize")
async def finalize(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    now = deps.clock.now()
    decision = state.get("analyst_decision", {}).get("decision")
    final = state.get("final_disposition")
    status = CaseStatus.RETURNED.value if decision == "reject" or not final else STATUS_BY_DISPOSITION[final]
    await deps.cases.update(state["case_id"], {"status": status, "final_disposition": final}, now)
    execs = await deps.node_execs.for_run(state["run_id"])
    totals = {
        "tokens": sum(int(e.get("tokens_in") or 0) + int(e.get("tokens_out") or 0) for e in execs),
        "latency_ms": sum(int(e.get("latency_ms") or 0) for e in execs),
        "retries": sum(int(e.get("retries") or 0) for e in execs),
        "fallback_nodes": sum(1 for e in execs if e.get("fallback_used")),
    }
    await deps.runs.update(state["run_id"], {"status": "completed", "ended_at": now, "totals": totals, "final_disposition": final}, now)
    head = await deps.audit.append(ts=now, actor={"type": "system", "id": "finalize"}, event="run.finalized", entity={"type": "case_run", "id": state["run_id"]}, case_id=state["case_id"], run_id=state["run_id"], payload={"status": status, "final_disposition": final, "totals": totals})
    return {META_KEY: {"summary": f"case {status}; audit head {head[:12]}"}}
