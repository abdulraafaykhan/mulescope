"""Investigation nodes: load_case, compute_metrics, profiler, flow_analyst,
aggregate_evidence and sufficiency_check.

Facts produced here have a stable ``key`` (for example ``metric:fan_in_count``)
and cite other facts by key. ``aggregate_evidence`` gives every new fact an
``EVD-`` id, resolves citations to ids, drops duplicates and writes the
evidence ledger.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig

from backend.app.agents.text import inr
from backend.app.agents.tools.flow_tools import FlowTools
from backend.app.core.errors import NotFound
from backend.app.domain.enums import CaseStatus
from backend.app.graph.deps import deps_of
from backend.app.graph.instrument import META_KEY, node
from backend.app.graph.state import CaseState

METRIC_TEXT: dict[str, str] = {
    "inflow_total": "Total credits in the window: {v}.",
    "outflow_total": "Total debits in the window: {v}.",
    "fan_in_count": "Distinct senders in the window: {v}.",
    "unrelated_sender_ratio": "Share of senders with no transaction with the account in the prior 90 days: {v}.",
    "repeat_sender_ratio": "Share of senders who also paid in the prior 90 days: {v}.",
    "median_exit_minutes": "Median minutes from a credit until an equal amount left the account: {v}.",
    "pass_through_ratio": "Share of inflow sent out within 24 hours of arriving: {v}.",
    "retention_ratio": "Median end-of-day balance divided by median daily inflow: {v}.",
    "turnover_multiple": "Monthly-equivalent credits divided by declared monthly turnover: {v}.",
    "account_age_days": "Account age at window start, in days: {v}.",
    "dormancy_days": "Days without activity before the window: {v}.",
    "cashout_share": "Share of outflow via ATM or wallet loads: {v}.",
    "beneficiary_concentration": "Share of outflow going to the top two beneficiaries: {v}.",
    "structured_amount_share": "Share of credits that are round or just under a limit: {v}.",
    "volume_zscore_vs_history": "Window volume z-score against the prior 90-day weekly mean: {v}.",
    "reciprocal_flow_share": "Share of outflow returned to the same senders: {v}.",
    "complaint_linked_senders": "Senders who appear in open fraud complaints: {v}.",
}
PERCENT_KEYS = {"unrelated_sender_ratio", "repeat_sender_ratio", "pass_through_ratio", "cashout_share", "beneficiary_concentration", "structured_amount_share", "reciprocal_flow_share"}
MONEY_KEYS = {"inflow_total", "outflow_total"}


def _fmt(key: str, value: Any) -> str:
    if key in MONEY_KEYS:
        return inr(float(value))
    if key in PERCENT_KEYS:
        return f"{float(value):.0%}"
    return f"{value}"


def _window(state: CaseState) -> tuple[datetime, datetime]:
    w = state["window"]
    return datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"])


@node("load_case")
async def load_case(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    case = await deps.cases.get(state["case_id"])
    if case is None:
        raise NotFound(f"case {state['case_id']} not found")
    alert = await deps.alerts.get(case["alert_id"])
    account = await deps.accounts.get(case["account_id"])
    if alert is None or account is None:
        raise NotFound("alert or account missing for case", detail={"case_id": state["case_id"]})
    customer = await deps.customers.get(account["customer_id"]) or {}
    await deps.cases.update(state["case_id"], {"status": CaseStatus.INVESTIGATING.value, "current_run_id": state["run_id"]}, deps.clock.now())
    window = {"start": alert["window"]["start"].isoformat(), "end": alert["window"]["end"].isoformat()}
    return {
        "alert": {k: v for k, v in alert.items() if k not in ("window", "created_at", "updated_at")},
        "account": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in account.items()},
        "customer": {"id": customer.get("id"), "kyc": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in customer.get("kyc", {}).items()}, "risk_rating": customer.get("risk_rating")},
        "window": window,
        "loop_counts": {"sufficiency": 0, "critic": 0, "request_more": 0},
        META_KEY: {"summary": f"loaded {case['account_id']}, window {window['start'][:10]} to {window['end'][:10]}"},
    }


@node("compute_metrics")
async def compute_metrics(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    start, end = _window(state)
    bundle = await deps.metrics.compute(state["account"]["id"], start, end)
    metrics = bundle.metrics.model_dump()
    facts = [
        {"key": f"metric:{k}", "kind": "metric", "source": "compute_metrics", "severity": "info", "statement": text.format(v=_fmt(k, metrics[k])), "data": {"metric": k, "value": metrics[k]}, "refs": [state["account"]["id"]], "cites": []}
        for k, text in METRIC_TEXT.items()
    ]
    return {"metrics": metrics, "facts": facts, META_KEY: {"summary": f"{metrics['credit_count']} credits, {metrics['fan_in_count']} senders, median exit {metrics['median_exit_minutes']:.0f} min"}}


@node("profiler", agent="profiler")
async def profiler(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    facts, finding, meta = await deps.agents.profiler.run(state["metrics"], state["account"], state["customer"])
    return {"facts": facts, "findings": {"profiler": finding}, META_KEY: meta}


@node("flow_analyst", agent="flow")
async def flow_analyst(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    start, end = _window(state)
    tools = FlowTools(deps.tx, deps.complaints, state["account"]["id"], start, end)
    remarks = await tools.credit_remarks()
    facts, finding, meta = await deps.agents.flow_analyst.run(tools, state["metrics"], remarks, state.get("gaps", []))
    return {"facts": facts, "findings": {"flow_analyst": finding}, META_KEY: meta}


@node("aggregate_evidence")
async def aggregate_evidence(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    existing = list(state.get("evidence", []))
    known = {e["key"] for e in existing}
    new: list[dict[str, Any]] = []
    for f in state.get("facts", []):
        if f["key"] not in known:
            known.add(f["key"])
            new.append(f)
    now = deps.clock.now()
    ids = await deps.counters.next_ids("evidence", "EVD-", len(new), now) if new else []
    key_to_id = {e["key"]: e["id"] for e in existing} | {f["key"]: i for f, i in zip(new, ids, strict=True)}
    docs = []
    for f, eid in zip(new, ids, strict=True):
        docs.append({
            "_id": eid, "case_id": state["case_id"], "run_id": state["run_id"], "key": f["key"], "kind": f["kind"], "source": f["source"],
            "statement": f["statement"], "data": f.get("data", {}), "severity": f.get("severity", "info"), "refs": [r for r in f.get("refs", []) if r],
            "cites": [key_to_id[k] for k in f.get("cites", []) if k in key_to_id], "created_at": now,
        })
    await deps.evidence.insert_many(docs)
    evidence = existing + [{("id" if k == "_id" else k): (v if k != "created_at" else v.isoformat()) for k, v in d.items()} for d in docs]
    return {"evidence": evidence, META_KEY: {"summary": f"{len(docs)} new evidence items, {len(evidence)} total"}}


@node("sufficiency_check")
async def sufficiency_check(state: CaseState, config: RunnableConfig) -> dict[str, Any]:
    deps = deps_of(config)
    kinds = {e["kind"] for e in state.get("evidence", [])}
    gaps = [k for k in deps.playbook.required_evidence_kinds if k not in kinds]
    loops = dict(state.get("loop_counts", {}))
    if gaps:
        loops["sufficiency"] = loops.get("sufficiency", 0) + 1
    return {"gaps": gaps, "loop_counts": loops, META_KEY: {"summary": "evidence sufficient" if not gaps else f"missing: {', '.join(gaps)}"}}
