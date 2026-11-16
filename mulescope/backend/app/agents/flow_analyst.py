"""Flow Analyst agent: who sent the money, where it went and how fast.

``TemplateFlowAnalyst`` (fallback) calls the read-only tools in a bounded
loop (at most four calls) and turns the results into facts. Transaction
remarks are only inspected by a code check for instruction-like text; they
are never followed.
"""

from __future__ import annotations

from typing import Any

from backend.app.agents.text import inr, looks_like_instruction
from backend.app.agents.tools.flow_tools import FlowTools

PROMPT_VERSION = "flow-template-1"
MAX_TOOL_CALLS = 4


class TemplateFlowAnalyst:
    """Rule-based flow review over the read-only tools."""

    name = "flow_analyst"

    async def run(self, tools: FlowTools, metrics: dict[str, Any], remarks: list[str], gaps: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        """Return ``(facts, finding, meta)``."""
        calls: list[dict[str, Any]] = []

        async def call(name: str) -> dict[str, Any]:
            result: dict[str, Any] = await getattr(tools, name)()
            calls.append({"tool": name, "args": {"account_id": tools.account_id}, "result": {k: (v if not isinstance(v, list) else v[:5]) for k, v in result.items()}})
            return result

        cps = await call("get_counterparties")
        path = await call("get_flow_path")
        overlap = await call("get_sender_overlap")
        complaints = await call("check_complaints")
        assert len(calls) <= MAX_TOOL_CALLS

        m = metrics
        receivers = cps["receivers"][:2]
        rec_text = ", ".join(f"{r['name']} ({inr(r['amount'])}, {r['count']} transfers)" for r in receivers) or "no outgoing transfers"
        facts: list[dict[str, Any]] = [
            {"key": "flow:fan_in", "kind": "flow", "source": "flow_analyst", "severity": "high" if m["fan_in_count"] >= 15 and m["unrelated_sender_ratio"] >= 0.7 else "info",
             "statement": f"{m['fan_in_count']} senders paid {inr(m['inflow_total'])} in {m['credit_count']} credits; {m['unrelated_sender_ratio']:.0%} had no dealings with the account in the prior 90 days.",
             "data": {"senders": cps["senders"][:5], "sender_count": cps["sender_count"]}, "refs": [s["ref"] for s in cps["senders"][:5]], "cites": ["metric:fan_in_count", "metric:unrelated_sender_ratio"]},
            {"key": "flow:exit_speed", "kind": "flow", "source": "flow_analyst", "severity": "high" if m["median_exit_minutes"] < 90 else "info",
             "statement": f"Money left a median of {m['median_exit_minutes']:.0f} minutes after it arrived; {m['pass_through_ratio']:.0%} of inflow went out within 24 hours.",
             "data": {"median_exit_minutes": m["median_exit_minutes"], "pass_through_ratio": m["pass_through_ratio"]}, "refs": [], "cites": ["metric:median_exit_minutes", "metric:pass_through_ratio"]},
            {"key": "flow:beneficiaries", "kind": "flow", "source": "flow_analyst", "severity": "medium" if m["beneficiary_concentration"] >= 0.7 else "info",
             "statement": f"{inr(m['outflow_total'])} went out; the top beneficiaries were {rec_text}, together {m['beneficiary_concentration']:.0%} of outflow.",
             "data": {"receivers": cps["receivers"][:5]}, "refs": [r["ref"] for r in receivers], "cites": ["metric:beneficiary_concentration"]},
        ]
        if m["cashout_share"] > 0:
            facts.append({"key": "flow:cashout", "kind": "flow", "source": "flow_analyst", "severity": "high" if m["cashout_share"] >= 0.4 else "low",
                          "statement": f"{m['cashout_share']:.0%} of outflow left as ATM cash or wallet loads.", "data": {"cashout_share": m["cashout_share"]}, "refs": [], "cites": ["metric:cashout_share"]})
        facts.append({"key": "complaint:check", "kind": "complaint_check", "source": "tool:check_complaints", "severity": "high" if complaints["count"] >= 3 else ("medium" if complaints["count"] else "info"),
                      "statement": f"{complaints['count']} open fraud complaint(s) name this account as beneficiary" + (f", from {len(complaints['victims'])} sender(s), totalling {inr(complaints['amount'])}." if complaints["count"] else "."),
                      "data": complaints, "refs": complaints["complaint_ids"], "cites": ["metric:complaint_linked_senders"]})
        if path["linked_accounts"]:
            facts.append({"key": "flow:linked_accounts", "kind": "flow", "source": "tool:get_flow_path", "severity": "medium",
                          "statement": f"Funds moved to or from {len(path['linked_accounts'])} other account(s) at our bank: {', '.join(path['linked_accounts'])}.", "data": path, "refs": path["linked_accounts"], "cites": []})
        if overlap["accounts"]:
            top = overlap["accounts"][0]
            facts.append({"key": "flow:sender_overlap", "kind": "flow", "source": "tool:get_sender_overlap", "severity": "low",
                          "statement": f"{len(overlap['accounts'])} other account(s) at our bank received money from the same senders (most: {top['account_id']}, {top['shared_senders']} shared senders).", "data": overlap, "refs": [a["account_id"] for a in overlap["accounts"]], "cites": []})
        flagged = [r for r in remarks if looks_like_instruction(r)]
        if flagged:
            facts.append({"key": "flow:remark_injection", "kind": "flow", "source": "flow_analyst", "severity": "medium",
                          "statement": f"{len(flagged)} transaction remark(s) contain text addressed to an automated reviewer. Remarks are treated as untrusted data and were not followed.", "data": {"count": len(flagged)}, "refs": [], "cites": []})
        finding = {"pattern": "rapid_pass_through" if m["median_exit_minutes"] < 90 else "slower_flow", "linked_accounts": path["linked_accounts"], "complaints": complaints["count"], "addressed_gaps": gaps, "cited_keys": [f["key"] for f in facts]}
        meta = {"fallback_used": True, "prompt_version": PROMPT_VERSION, "model": "template", "tool_calls": calls, "summary": f"{len(calls)} tool calls, {len(facts)} facts"}
        return facts, finding, meta
