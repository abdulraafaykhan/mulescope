"""Read models for the analyst UI: queue, case detail, money flow, timeline,
transactions, evidence, report, actions, account summary and diagnostics.

Everything the UI renders is shaped here, so the frontend never aggregates raw
ledger rows. Uses the repositories only; no business decisions.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from backend.app.core.clock import Clock
from backend.app.core.errors import NotFound
from backend.app.services.metrics_service import party_key

IST = timedelta(hours=5, minutes=30)
TOP_SENDERS = 24
TOP_RECEIVERS = 12
OPEN_STATUSES = {"new", "investigating", "awaiting_decision", "returned"}


class CaseQueryService:
    """Builds read models."""

    def __init__(self, *, cases: Any, alerts: Any, accounts: Any, customers: Any, tx: Any, evidence: Any, reports: Any, actions: Any, decisions: Any, runs: Any, node_execs: Any, complaints: Any, clock: Clock) -> None:
        self.cases, self.alerts, self.accounts, self.customers, self.tx = cases, alerts, accounts, customers, tx
        self.evidence, self.reports, self.actions, self.decisions = evidence, reports, actions, decisions
        self.runs, self.node_execs, self.complaints, self.clock = runs, node_execs, complaints, clock

    # --- queue ---------------------------------------------------------------

    async def queue(self, status: str | None, priority: int | None) -> dict[str, Any]:
        cases = await self.cases.list(status=status, priority=priority)
        accounts = await self.accounts.many([c["account_id"] for c in cases])
        customers = await self.customers.many(list({a["customer_id"] for a in accounts.values()}))
        alerts = {a["id"]: a for a in await self.alerts.list(limit=10_000)}
        runs = await self.runs.latest_for_cases([c["id"] for c in cases])
        now = self.clock.now()
        rows = []
        for c in cases:
            acct = accounts.get(c["account_id"], {})
            cust = customers.get(acct.get("customer_id", ""), {})
            alert = alerts.get(c["alert_id"], {})
            tm = alert.get("trigger_metrics", {})
            run = runs.get(c["id"], {})
            rows.append({
                "case_id": c["id"], "alert_id": c["alert_id"], "account_id": c["account_id"], "account_masked": acct.get("account_no_masked"),
                "holder_name": acct.get("holder_name"), "customer_name": cust.get("kyc", {}).get("name"), "occupation": cust.get("kyc", {}).get("occupation"),
                "score": c.get("score"), "recommended_disposition": c.get("recommended_disposition"), "final_disposition": c.get("final_disposition"),
                "status": c["status"], "priority": c["priority"], "sla_due_at": c.get("sla_due_at"), "assigned_to": c.get("assigned_to"),
                "inflow": tm.get("inflow"), "senders": tm.get("distinct_senders"), "rule_id": alert.get("rule_id"), "created_at": c.get("created_at"),
                "current_run_id": c.get("current_run_id"), "run_status": run.get("status"), "llm_mode": run.get("llm_mode"),
            })
        kpis = {
            "open_cases": sum(1 for c in cases if c["status"] in OPEN_STATUSES),
            "sla_breaching": sum(1 for c in cases if c["status"] in OPEN_STATUSES and c.get("sla_due_at") and c["sla_due_at"] < now),
            "awaiting_decision": sum(1 for c in cases if c["status"] == "awaiting_decision"),
            "fallback_runs": sum(1 for r in runs.values() if r.get("llm_mode") == "fallback"),
            "total_cases": len(cases),
        }
        return {"kpis": kpis, "items": rows}

    # --- case ----------------------------------------------------------------

    async def _case(self, case_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], datetime, datetime]:
        case = await self.cases.get(case_id)
        if case is None:
            raise NotFound(f"case {case_id} not found", detail={"case_id": case_id})
        alert = await self.alerts.get(case["alert_id"]) or {}
        account = await self.accounts.get(case["account_id"]) or {}
        return case, alert, account, alert["window"]["start"], alert["window"]["end"]

    async def detail(self, case_id: str) -> dict[str, Any]:
        case, alert, account, start, end = await self._case(case_id)
        customer = await self.customers.get(account.get("customer_id", "")) or {}
        run = await self.runs.latest_for_case(case_id)
        rows = await self.tx.ledger(case["account_id"], start, end)
        strip = _entity_strip(rows, account, customer)
        decisions = await self.decisions.for_case(case_id)
        return {"case": case, "alert": alert, "account": account, "customer": customer, "run": run, "entity_strip": strip, "decisions": decisions}

    async def flow(self, case_id: str) -> dict[str, Any]:
        case, _, account, start, end = await self._case(case_id)
        rows = await self.tx.ledger(case["account_id"], start, end)
        return _flow_graph(rows, account)

    async def timeline(self, case_id: str) -> dict[str, Any]:
        case, _, _, start, end = await self._case(case_id)
        rows = await self.tx.ledger(case["account_id"], start, end)
        days: dict[str, dict[str, Any]] = {}
        d = start
        while d < end:
            key = (d + IST).date().isoformat()
            days[key] = {"date": key, "inflow": 0.0, "outflow": 0.0, "credits": 0, "debits": 0, "balance": None}
            d += timedelta(days=1)
        for r in rows:
            key = (r["ts"] + IST).date().isoformat()
            day = days.setdefault(key, {"date": key, "inflow": 0.0, "outflow": 0.0, "credits": 0, "debits": 0, "balance": None})
            if r["direction"] == "credit":
                day["inflow"] += r["amount"]
                day["credits"] += 1
            else:
                day["outflow"] += r["amount"]
                day["debits"] += 1
            day["balance"] = r["balance_after"]
        last = None
        for day in days.values():
            if day["balance"] is None:
                day["balance"] = last
            last = day["balance"]
        events = [{"ts": r["ts"], "direction": r["direction"], "amount": r["amount"], "balance": r["balance_after"], "channel": r["channel"]} for r in rows]
        return {"days": sorted(days.values(), key=lambda x: x["date"]), "events": events}

    async def transactions(self, case_id: str, cursor: str | None, limit: int) -> dict[str, Any]:
        case, _, _, start, end = await self._case(case_id)
        items, nxt = await self.tx.page(case["account_id"], start, end, cursor, limit)
        run = await self.runs.latest_for_case(case_id)
        evidence = await self.evidence.for_run(case_id, run["id"]) if run else []
        by_ref: dict[str, list[str]] = defaultdict(list)
        for e in evidence:
            for ref in e.get("refs", []):
                by_ref[ref].append(e["id"])
        for it in items:
            it["evidence_ids"] = sorted(set(by_ref.get(party_key(it), []) + by_ref.get(it.get("transfer_id") or "", [])))
        return {"items": items, "next_cursor": nxt}

    async def evidence_list(self, case_id: str) -> list[dict[str, Any]]:
        run = await self.runs.latest_for_case(case_id)
        return await self.evidence.for_run(case_id, run["id"]) if run else []

    async def report(self, case_id: str) -> dict[str, Any] | None:
        return await self.reports.latest(case_id)

    async def actions_for(self, case_id: str) -> list[dict[str, Any]]:
        return await self.actions.for_case(case_id)

    async def diagnostics(self, run_id: str) -> dict[str, Any]:
        run = await self.runs.get(run_id)
        if run is None:
            raise NotFound(f"run {run_id} not found")
        nodes = await self.node_execs.for_run(run_id)
        tokens: dict[str, int] = defaultdict(int)
        for n in nodes:
            tokens[n["agent"]] += int(n.get("tokens_in") or 0) + int(n.get("tokens_out") or 0)
        return {"run": run, "nodes": nodes, "tokens_by_agent": dict(tokens), "fallback_used": any(n.get("fallback_used") for n in nodes), "total_latency_ms": sum(int(n.get("latency_ms") or 0) for n in nodes)}

    async def account_summary(self, account_id: str) -> dict[str, Any]:
        account = await self.accounts.get(account_id)
        if account is None:
            raise NotFound(f"account {account_id} not found")
        customer = await self.customers.get(account["customer_id"]) or {}
        last = await self.tx.last_before(account_id, self.clock.now() + timedelta(days=3650))
        end = (last["ts"] + timedelta(seconds=1)) if last else self.clock.now()
        start = end - timedelta(days=104)
        rows = await self.tx.ledger(account_id, start, end)
        window_start = end - timedelta(days=14)
        prior = [r for r in rows if r["ts"] < window_start]
        window = [r for r in rows if r["ts"] >= window_start]

        def weekly(rs: list[dict[str, Any]], days: float, direction: str) -> float:
            return round(sum(r["amount"] for r in rs if r["direction"] == direction) / max(days / 7, 1), 2)

        spark: dict[str, float] = {}
        for r in rows:
            spark[(r["ts"] + IST).date().isoformat()] = r["balance_after"]
        complaints = await self.complaints.for_beneficiary(account_id)
        cases = await self.cases.for_account(account_id)
        return {
            "account": account, "customer": customer,
            "baseline": {"prior_weekly_inflow": weekly(prior, 90, "credit"), "prior_weekly_outflow": weekly(prior, 90, "debit"), "window_weekly_inflow": weekly(window, 14, "credit"), "window_weekly_outflow": weekly(window, 14, "debit")},
            "balance_sparkline": [{"date": k, "balance": v} for k, v in sorted(spark.items())],
            "complaints": complaints, "cases": [{"case_id": c["id"], "status": c["status"], "score": c.get("score")} for c in cases],
            "recent_transactions": list(reversed(rows[-15:])),
        }


def _entity_strip(rows: list[dict[str, Any]], account: dict[str, Any], customer: dict[str, Any]) -> dict[str, Any]:
    senders: dict[str, dict[str, Any]] = defaultdict(lambda: {"amount": 0.0, "count": 0})
    receivers: dict[str, dict[str, Any]] = defaultdict(lambda: {"amount": 0.0, "count": 0, "channels": set()})
    for r in rows:
        book = senders if r["direction"] == "credit" else receivers
        k = party_key(r)
        book[k]["amount"] += r["amount"]
        book[k]["count"] += 1
        book[k]["name"] = r["cp_name"]
        book[k]["type"] = r["cp_type"]
        if r["direction"] == "debit":
            receivers[k]["channels"].add(r["channel"])
    total_in = sum(v["amount"] for v in senders.values())
    total_out = sum(v["amount"] for v in receivers.values())
    kyc = customer.get("kyc", {})

    def top(book: dict[str, dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
        return [{"ref": k, "name": v["name"], "amount": round(v["amount"], 2), "count": v["count"], "type": v["type"]} for k, v in sorted(book.items(), key=lambda kv: -kv[1]["amount"])[:n]]

    channels = sorted({c for v in receivers.values() for c in v["channels"]})
    return {
        "senders": {"count": len(senders), "total": round(total_in, 2), "top": top(senders)},
        "mule": {"account_id": account.get("id"), "name": account.get("holder_name"), "account_masked": account.get("account_no_masked"), "occupation": kyc.get("occupation"),
                 "declared_income": kyc.get("declared_income"), "declared_monthly_turnover": account.get("declared_monthly_turnover"), "window_inflow": round(total_in, 2),
                 "opened_at": account.get("opened_at"), "balance": account.get("balance"), "kyc_status": kyc.get("kyc_status")},
        "receivers": {"count": len(receivers), "total": round(total_out, 2), "channels": channels, "top": top(receivers)},
    }


def _flow_graph(rows: list[dict[str, Any]], account: dict[str, Any]) -> dict[str, Any]:
    """Senders on the left, the account in the centre, receivers on the right."""
    centre = account.get("id", "account")
    ins: dict[str, dict[str, Any]] = defaultdict(lambda: {"amount": 0.0, "count": 0, "first": None})
    outs: dict[str, dict[str, Any]] = defaultdict(lambda: {"amount": 0.0, "count": 0, "first": None})
    credit_times: list[datetime] = []
    exit_gaps: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        k = party_key(r)
        book = ins if r["direction"] == "credit" else outs
        book[k]["amount"] += r["amount"]
        book[k]["count"] += 1
        book[k]["name"] = r["cp_name"]
        book[k]["type"] = r["cp_type"]
        book[k]["channel"] = r["channel"]
        book[k]["first"] = book[k]["first"] or r["ts"]
        if r["direction"] == "credit":
            credit_times.append(r["ts"])
        elif credit_times:
            exit_gaps[k].append((r["ts"] - credit_times[-1]).total_seconds() / 60)

    def bucket(book: dict[str, dict[str, Any]], n: int, side: str) -> list[tuple[str, dict[str, Any]]]:
        ranked = sorted(book.items(), key=lambda kv: -kv[1]["amount"])
        head, tail = ranked[:n], ranked[n:]
        if tail:
            head.append((f"{side}-others", {"amount": sum(v["amount"] for _, v in tail), "count": sum(v["count"] for _, v in tail), "name": f"{len(tail)} more", "type": "group", "channel": None, "first": None}))
        return head

    nodes = [{"id": centre, "role": "mule", "label": account.get("holder_name"), "sublabel": account.get("account_no_masked"), "amount": round(sum(v["amount"] for v in ins.values()), 2), "count": sum(v["count"] for v in ins.values()), "balance": account.get("balance"), "opened_at": account.get("opened_at")}]
    edges = []
    for k, v in bucket(ins, TOP_SENDERS, "senders"):
        nid = f"in:{k}"
        nodes.append({"id": nid, "role": "sender", "ref": k, "label": v["name"], "sublabel": v.get("type"), "amount": round(v["amount"], 2), "count": v["count"], "first_ts": v.get("first")})
        edges.append({"id": f"e-{nid}", "source": nid, "target": centre, "amount": round(v["amount"], 2), "count": v["count"], "channel": v.get("channel"), "exit_minutes": None})
    for k, v in bucket(outs, TOP_RECEIVERS, "receivers"):
        nid = f"out:{k}"
        gaps = exit_gaps.get(k, [])
        median = sorted(gaps)[len(gaps) // 2] if gaps else None
        nodes.append({"id": nid, "role": "receiver", "ref": k, "label": v["name"], "sublabel": v.get("type"), "amount": round(v["amount"], 2), "count": v["count"], "first_ts": v.get("first")})
        edges.append({"id": f"e-{nid}", "source": centre, "target": nid, "amount": round(v["amount"], 2), "count": v["count"], "channel": v.get("channel"), "exit_minutes": round(median, 1) if median is not None else None})
    return {"nodes": nodes, "edges": edges}
