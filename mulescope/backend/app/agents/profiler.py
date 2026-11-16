"""Profiler agent: compares the KYC profile with the observed behaviour.

``TemplateProfiler`` is the deterministic implementation used in fallback
mode (and whenever an LLM call fails). It returns facts (to become evidence)
and a structured ``ProfilerFinding``. Facts cite metric facts by key; the
aggregate node turns keys into ``EVD-`` ids.
"""

from __future__ import annotations

from typing import Any

from backend.app.agents.text import inr

PROMPT_VERSION = "profiler-template-1"


class TemplateProfiler:
    """Rule-based profile review."""

    name = "profiler"

    async def run(self, metrics: dict[str, Any], account: dict[str, Any], customer: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        """Return ``(facts, finding, meta)``."""
        kyc = customer.get("kyc", {})
        occupation = kyc.get("occupation", "unknown occupation")
        declared = metrics.get("declared_monthly_turnover", 0.0)
        monthly = metrics["inflow_total"] * 30 / max(metrics["window_days"], 1)
        multiple = metrics["turnover_multiple"]
        facts = [
            {
                "key": "profile:kyc", "kind": "profile", "source": "profiler", "severity": "info",
                "statement": f"KYC records the customer as {occupation} in {kyc.get('city', 'an unknown city')}, declared income {inr(kyc.get('declared_income', 0.0))} a year and declared turnover {inr(declared)} a month; KYC status {kyc.get('kyc_status', 'unknown')}.",
                "data": {"occupation": occupation, "declared_income": kyc.get("declared_income"), "declared_turnover": declared, "kyc_status": kyc.get("kyc_status")},
                "refs": [customer.get("id", "")], "cites": [],
            },
            {
                "key": "profile:turnover", "kind": "profile", "source": "profiler", "severity": "high" if multiple >= 10 else "low",
                "statement": f"Window credits are equivalent to {inr(monthly)} a month, {multiple:.1f} times the declared turnover.",
                "data": {"monthly_equivalent": round(monthly, 2), "turnover_multiple": multiple}, "refs": [account.get("id", "")], "cites": ["metric:turnover_multiple"],
            },
            {
                "key": "profile:age", "kind": "profile", "source": "profiler", "severity": "medium" if metrics["account_age_days"] < 180 or metrics["dormancy_days"] > 180 else "info",
                "statement": f"The account was {metrics['account_age_days']} days old at the start of the window and had been inactive for {metrics['dormancy_days']} days before it.",
                "data": {"account_age_days": metrics["account_age_days"], "dormancy_days": metrics["dormancy_days"]}, "refs": [account.get("id", "")], "cites": ["metric:account_age_days"],
            },
        ]
        if kyc.get("kyc_status") not in (None, "verified"):
            facts.append({
                "key": "profile:kyc_stale", "kind": "profile", "source": "profiler", "severity": "medium",
                "statement": f"KYC is not current (status {kyc.get('kyc_status')}).", "data": {"kyc_refreshed_at": str(kyc.get("kyc_refreshed_at"))}, "refs": [customer.get("id", "")], "cites": [],
            })
        mismatches = [f["statement"] for f in facts if f["severity"] in ("high", "medium")]
        plausibility = "low" if multiple >= 10 else ("medium" if multiple >= 3 else "high")
        finding = {"mismatches": mismatches, "plausibility": plausibility, "confidence": 0.7, "cited_keys": [f["key"] for f in facts]}
        meta = {"fallback_used": True, "prompt_version": PROMPT_VERSION, "model": "template", "summary": f"profile plausibility {plausibility}; {len(mismatches)} mismatch(es)"}
        return facts, finding, meta
