"""Critic: code-level checks on the draft (plus an LLM review in live mode).

Code checks (always run):
* every cited ``EVD-`` id exists in the evidence ledger;
* every claim sentence carries at least one citation;
* the disposition stated in the narrative equals the policy disposition;
* the STR narrative contains every required section;
* customer-facing text contains no tipping-off terms.
"""

from __future__ import annotations

import re
from typing import Any

PROMPT_VERSION = "critic-template-1"
_EVD = re.compile(r"EVD-\d{6}")
_STATED = re.compile(r"Recommended disposition: \*\*(.+?)\*\*")
MIN_CLAIM_CHARS = 40
LABEL_TO_DISP = {"CLOSE": "close", "ESCALATE": "escalate", "STR DRAFT": "str_draft"}


def _claims(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or len(s) < MIN_CLAIM_CHARS:
            continue
        out.append(s)
    return out


def code_checks(report: dict[str, Any], evidence_ids: set[str], policy_disposition: str, tipping_terms: list[str], str_sections: list[str]) -> list[str]:
    """Return the list of issues found by deterministic checks."""
    issues: list[str] = []
    texts = [report.get("summary_md") or "", report.get("str_narrative_md") or ""]
    cited = {c for t in texts for c in _EVD.findall(t)}
    unknown = sorted(cited - evidence_ids)
    if unknown:
        issues.append(f"cites unknown evidence ids: {', '.join(unknown[:5])}")
    uncited = [c for t in texts for c in _claims(t) if not _EVD.search(c)]
    if uncited:
        issues.append(f"{len(uncited)} claim sentence(s) without a citation, e.g. '{uncited[0][:80]}'")
    stated = _STATED.search(texts[0])
    if not stated or LABEL_TO_DISP.get(stated.group(1).strip()) != policy_disposition:
        issues.append("narrative disposition does not match the policy disposition")
    if policy_disposition == "str_draft":
        body = texts[1]
        missing = [s for s in str_sections if f"**{s}:**" not in body]
        if missing:
            issues.append(f"STR narrative misses sections: {', '.join(missing)}")
    customer = (report.get("customer_query_md") or "").lower()
    hits = [t for t in tipping_terms if re.search(rf"\b{re.escape(t.lower())}\b", customer)]
    if hits:
        issues.append(f"customer text contains tipping-off terms: {', '.join(hits)}")
    return issues


class TemplateCritic:
    """Code checks only (fallback mode)."""

    name = "critic"

    async def run(self, report: dict[str, Any], evidence: list[dict[str, Any]], policy: dict[str, Any], tipping_terms: list[str], str_sections: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        issues = code_checks(report, {e["id"] for e in evidence}, policy["disposition"], tipping_terms, str_sections)
        result = {"verdict": "revise" if issues else "pass", "issues": issues, "checks": "code"}
        meta = {"fallback_used": True, "prompt_version": PROMPT_VERSION, "model": "template", "summary": f"{result['verdict']}: {len(issues)} issue(s)"}
        return result, meta
