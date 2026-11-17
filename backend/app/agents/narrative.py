"""Narrative Writer: case summary, STR narrative and customer clarification draft.

It sees only the evidence ledger, the policy result and the proposed actions,
never raw transactions. Every sentence carries ``EVD-`` citations. The
template writer is used in fallback mode and when an LLM call fails.
"""

from __future__ import annotations

from typing import Any

from backend.app.agents.text import cite, inr, ist, strip_unknown_ids

PROMPT_VERSION = "narrative-template-1"
DISPOSITION_LABEL = {"close": "CLOSE", "escalate": "ESCALATE", "str_draft": "STR DRAFT"}


class TemplateNarrativeWriter:
    """Deterministic narrative built from evidence statements."""

    name = "narrative_writer"

    async def run(self, *, evidence: list[dict[str, Any]], policy: dict[str, Any], actions: list[dict[str, Any]], account: dict[str, Any], customer: dict[str, Any], window: dict[str, str], issues: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(report, meta)``."""
        by_key = {e["key"]: e for e in evidence}

        def eid(*keys: str) -> str:
            return cite(*[by_key[k]["id"] for k in keys if k in by_key])

        def stmt(key: str) -> str | None:
            """Evidence statement with its citation, or None when absent."""
            e = by_key.get(key)
            return f"{e['statement']} {cite(e['id'])}" if e else None

        def s(key: str) -> str:
            return stmt(key) or ""

        name = customer.get("kyc", {}).get("name", account.get("holder_name", "The customer"))
        masked = account.get("account_no_masked", "")
        disp = policy["disposition"]
        label = DISPOSITION_LABEL[disp]
        signal_ids = [e["id"] for e in evidence if e["kind"] == "signal" and e.get("data", {}).get("fired") and e.get("data", {}).get("kind") == "risk"]
        mitigator_ids = [e["id"] for e in evidence if e["kind"] == "signal" and e.get("data", {}).get("fired") and e.get("data", {}).get("kind") == "mitigator"]
        period = f"{ist(window['start'])} to {ist(window['end'])}"
        m = {k: by_key[k]["data"].get("value") for k in by_key if k.startswith("metric:")}

        summary = [
            "## Executive summary",
            f"{name} (account {masked}) received {inr(m.get('inflow_total') or 0)} and sent {inr(m.get('outflow_total') or 0)} between {period}. {eid('metric:inflow_total', 'metric:outflow_total')}",
            stmt("flow:fan_in"),
            stmt("flow:exit_speed"),
            stmt("flow:beneficiaries"),
            "",
            "## Findings",
            "### Profile vs behaviour",
            stmt("profile:kyc"),
            stmt("profile:turnover"),
            stmt("profile:age"),
            stmt("profile:kyc_stale"),
            "### Flow pattern",
            stmt("flow:cashout"),
            stmt("complaint:check"),
            stmt("flow:linked_accounts"),
            stmt("flow:sender_overlap"),
            stmt("flow:remark_injection"),
            "",
            "## Risk score",
            f"The deterministic policy scored the case {policy['score']:.0f} out of 100 from {len(policy['fired_signals'])} risk signal(s) and {len(policy['mitigators'])} mitigator(s). {cite(*signal_ids, *mitigator_ids)}",
            "",
            "## Typologies",
            *[f"- **{t['label']}**: {t['description']} {cite(*signal_ids)}" for t in policy.get("typologies", [])],
            *([] if policy.get("typologies") else ["- None matched."]),
            "",
            "## Recommended disposition and actions",
            f"Recommended disposition: **{label}**. {'; '.join(policy['reasons'])}. {cite(*signal_ids)}",
            *[f"- {a['type']} ({a['owner_role']}, due in {a['due_in_days']} days): {a['description']}. {cite(*a.get('evidence_ids', []))}" for a in actions],
        ]
        summary_md = "\n".join(line for line in summary if line is not None)

        str_md = None
        if disp == "str_draft":
            str_md = "\n".join([
                "## STR narrative (draft for maker-checker review)",
                f"**Who:** {name}, holder of account {masked} at our bank. {eid('profile:kyc')}",
                f"**What:** {s('flow:fan_in')}",
                f"**When:** Activity took place between {period}. {eid('metric:inflow_total')}",
                f"**Where:** Credits arrived by UPI and IMPS from accounts at other banks and left to the beneficiaries listed below. {eid('flow:beneficiaries')}",
                f"**How:** {s('flow:exit_speed')}",
                f"**Why suspicious:** {s('profile:turnover')} {s('complaint:check')}",
                f"**Amounts:** Total credits {inr(m.get('inflow_total') or 0)}; total debits {inr(m.get('outflow_total') or 0)}. {eid('metric:inflow_total', 'metric:outflow_total')}",
                f"**Accounts:** {s('flow:beneficiaries')} {s('flow:linked_accounts')}",
            ])

        customer_md = None
        if disp == "escalate":
            first = name.split()[0] if name else "Customer"
            customer_md = (
                f"Dear {first},\n\nAs part of a routine review of account activity, we would be grateful if you could tell us "
                f"the nature and source of the incoming payments to your account ending {masked[-4:]} between {period}, "
                "and the purpose of the related outgoing transfers. Supporting documents such as invoices or agreements are welcome.\n\n"
                "Please reply within 7 days through your branch or the secure message centre.\n\nThank you,\nCustomer Care"
            )
        valid = {e["id"] for e in evidence}
        summary_md = strip_unknown_ids(summary_md, valid)
        str_md = strip_unknown_ids(str_md, valid) if str_md else None
        customer_md = strip_unknown_ids(customer_md, valid) if customer_md else None
        citations = sorted({c for text in (summary_md, str_md or "") for c in _ids(text)})
        report = {"summary_md": summary_md, "str_narrative_md": str_md, "customer_query_md": customer_md, "citations": citations, "disposition_stated": disp, "addressed_issues": issues}
        meta = {"fallback_used": True, "prompt_version": PROMPT_VERSION, "model": "template", "summary": f"{len(citations)} citations, {label}"}
        return report, meta


def _ids(text: str) -> list[str]:
    import re

    return re.findall(r"EVD-\d{6}", text)
