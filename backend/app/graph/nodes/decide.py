"""Decision nodes: score_and_policy, plan_actions, narrative_writer, critic.

``score_and_policy`` is the only place a disposition is decided (pure domain
functions). Fired signals and mitigators become evidence so the narrative and
actions can cite them.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from backend.app.domain.metrics import FlowMetrics
from backend.app.domain.policy.action_planner import PlanContext, plan
from backend.app.domain.policy.disposition import PolicyResult, decide
from backend.app.domain.policy.scoring import score
from backend.app.graph.deps import GraphDeps, deps_of
from backend.app.graph.instrument import META_KEY, node
from backend.app.graph.state import CaseState


@node("score_and_policy")
async def score_and_policy(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    metrics = FlowMetrics(**state["metrics"])
    result = score(metrics, deps.scoring)
    policy = decide(result, metrics, deps.scoring)
    evidence = list(state.get("evidence", []))
    key_to_id = {e["key"]: e["id"] for e in evidence}
    hits = [h for h in result.hits if h.fired and f"signal:{h.name}" not in key_to_id]
    now = deps.clock.now()
    ids = await deps.counters.next_ids("evidence", "EVD-", len(hits), now) if hits else []
    docs = []
    for h, eid in zip(hits, ids, strict=True):
        rule = (deps.scoring.signals | deps.scoring.mitigators)[h.name]
        sign = "+" if h.kind == "risk" else "-"
        docs.append({
            "_id": eid, "case_id": state["case_id"], "run_id": state["run_id"], "key": f"signal:{h.name}", "kind": "signal", "source": "score_and_policy",
            "statement": f"{rule.description}: {h.reason} ({sign}{h.points:.0f} points).", "data": {"name": h.name, "kind": h.kind, "points": h.points, "fired": True},
            "severity": "high" if h.kind == "risk" and h.points >= 15 else ("medium" if h.kind == "risk" else "info"), "refs": [],
            "cites": [key_to_id[f"metric:{k}"] for k in h.metric_keys if f"metric:{k}" in key_to_id], "created_at": now,
        })
    await deps.evidence.insert_many(docs)
    evidence += [{("id" if k == "_id" else k): (v if k != "created_at" else v.isoformat()) for k, v in d.items()} for d in docs]
    await deps.cases.update(state["case_id"], {"score": policy.score, "recommended_disposition": policy.disposition.value, "typologies": [t.label for t in policy.typologies]}, now)
    dumped = policy.model_dump(mode="json")
    return {"policy": dumped, "typologies": dumped["typologies"], "evidence": evidence, META_KEY: {"summary": f"score {policy.score:.0f}, {policy.disposition.value}"}}


async def _persist_actions(deps: GraphDeps, state: CaseState, policy: PolicyResult) -> list[dict[str, Any]]:
    linked = state.get("findings", {}).get("flow_analyst", {}).get("linked_accounts", [])
    kyc_status = state["customer"].get("kyc", {}).get("kyc_status")
    ctx = PlanContext(case_id=state["case_id"], account_id=state["account"]["id"], inflow_total=state["metrics"]["inflow_total"], stale_kyc=kyc_status not in (None, "verified"), linked_accounts=linked)
    proposed = plan(policy, ctx, deps.playbook)
    signal_ids = [e["id"] for e in state.get("evidence", []) if e["kind"] == "signal" and e.get("data", {}).get("kind") == "risk"]
    now = deps.clock.now()
    ids = await deps.counters.next_ids("actions", "ACT-", len(proposed), now, width=5) if proposed else []
    for action, aid in zip(proposed, ids, strict=True):
        due = now.timestamp() + action.due_in_days * 86_400
        inserted = await deps.actions.upsert_proposed({
            "_id": aid, "case_id": state["case_id"], "run_id": state["run_id"], **action.model_dump(), "status": "proposed",
            "proposed_by": "plan_actions", "approved_by": None, "due_at": now.fromtimestamp(due, tz=now.tzinfo), "executed_at": None, "result": None,
            "evidence_ids": signal_ids, "history": [{"ts": now, "status": "proposed", "by": "plan_actions"}], "created_at": now, "updated_at": now, "schema_version": 1,
        })
        if not inserted:
            # Same key from an earlier run: move a still-proposed action to this run's ledger.
            await deps.actions.refresh_proposed(action.idempotency_key, state["run_id"], signal_ids, now)
    keys = {a.idempotency_key for a in proposed}
    rows = [a for a in await deps.actions.for_case(state["case_id"]) if a["idempotency_key"] in keys]
    return with_current_evidence(rows, state)


def with_current_evidence(rows: list[dict[str, Any]], state: CaseState) -> list[dict[str, Any]]:
    """Copy action rows with ``evidence_ids`` limited to the current run's ledger.

    Why: approved or executed actions keep the ids of the run that created
    them, and those ids are not in this run's ledger. Only the copy sent on to
    the narrative and critic changes; stored history is never rewritten.
    Falls back to the current risk-signal ids when nothing is left.
    """
    evidence = state.get("evidence", [])
    ledger = {e["id"] for e in evidence}
    signal_ids = [e["id"] for e in evidence if e["kind"] == "signal" and e.get("data", {}).get("kind") == "risk"]
    return [{**r, "evidence_ids": [i for i in r.get("evidence_ids", []) if i in ledger] or signal_ids} for r in rows]


def _jsonable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        out.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items() if k != "history"})
    return out


@node("plan_actions")
async def plan_actions(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    policy = PolicyResult(**state["policy"])
    actions = await _persist_actions(deps, state, policy)
    return {"proposed_actions": _jsonable(actions), META_KEY: {"summary": f"{len(actions)} actions proposed"}}


@node("narrative_writer", agent="narrative")
async def narrative_writer(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    issues = state.get("critic_result", {}).get("issues", []) if state.get("critic_result") else []
    report, meta = await deps.agents.narrative.run(
        evidence=state["evidence"], policy=state["policy"], actions=state.get("proposed_actions", []), account=state["account"], customer=state["customer"], window=state["window"], issues=issues,
    )
    now = deps.clock.now()
    version = await deps.reports.next_version(state["case_id"])
    rid = (await deps.counters.next_ids("reports", "RPT-", 1, now, width=5))[0]
    doc = {"_id": rid, "case_id": state["case_id"], "run_id": state["run_id"], "version": version, **report, "critic": None, "status": "draft", "created_at": now}
    await deps.reports.insert(doc)
    return {"report": {"id": rid, "version": version, **report}, META_KEY: meta}


@node("critic", agent="critic")
async def critic(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    result, meta = await deps.agents.critic.run(state["report"], state["evidence"], state["policy"], deps.playbook.tipping_off_terms, deps.playbook.str_required_sections)
    await deps.reports.update(state["report"]["id"], {"critic": result, "status": "reviewed" if result["verdict"] == "pass" else "needs_revision"})
    loops = dict(state.get("loop_counts", {}))
    if result["verdict"] != "pass":
        loops["critic"] = loops.get("critic", 0) + 1
    return {"critic_result": result, "loop_counts": loops, META_KEY: meta}
