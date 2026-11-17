"""Live Narrative Writer (Gemini) and Critic (Groq).

The narrative LLM writes the executive summary, findings, STR sections and
the customer letter as sentences that each carry evidence ids. Code then
assembles the report: ids not in the ledger are dropped, uncited sentences
are dropped, and the risk score, typologies, disposition line and actions
come from the template, so the stated disposition always equals the policy.
A customer letter with a tipping-off term is replaced by the neutral
template. The critic always runs the code checks and adds an LLM review.
"""

from __future__ import annotations

import re
from typing import Any

from backend.app.agents.critic import code_checks
from backend.app.agents.narrative import TemplateNarrativeWriter, _ids
from backend.app.agents.prompts import load_prompt
from backend.app.agents.schemas import CriticOutput, NarrativeOutput, Sentence
from backend.app.agents.text import cite, fallback_reason, strip_unknown_ids
from backend.app.core.config_files import AgentModelConfig
from backend.app.core.errors import LLMUnavailable
from backend.app.llm.client import LlmClient

RISK_SECTION = "\n## Risk score"
MAX_EVIDENCE_CHARS = 9000


def _render(sentences: list[Sentence], valid: set[str]) -> list[str]:
    out = []
    for s in sentences:
        ids = [i for i in s.evidence_ids if i in valid]
        if ids:
            out.append(f"{strip_unknown_ids(s.text, valid).strip()} {cite(*ids)}")
    return out


def _evidence_block(evidence: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {e['id']} [{e['kind']}]: {e['statement']}" for e in evidence)[:MAX_EVIDENCE_CHARS]


def _has_terms(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(re.search(rf"\b{re.escape(t.lower())}\b", low) for t in terms)


class LiveNarrativeWriter:
    """Gemini narrative with code-side assembly and guards."""

    name = "narrative_writer"

    def __init__(self, client: LlmClient, route: AgentModelConfig, str_sections: list[str], tipping_terms: list[str]) -> None:
        self._client, self._route, self._template = client, route, TemplateNarrativeWriter()
        self._sections, self._terms = str_sections, tipping_terms
        self.prompt_version, self._system = load_prompt("narrative_writer")

    async def run(self, *, evidence: list[dict[str, Any]], policy: dict[str, Any], actions: list[dict[str, Any]], account: dict[str, Any], customer: dict[str, Any], window: dict[str, str], issues: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        base, meta = await self._template.run(evidence=evidence, policy=policy, actions=actions, account=account, customer=customer, window=window, issues=issues)
        disp = policy["disposition"]
        user = (
            f"Customer: {customer.get('kyc', {}).get('name')}, account {account.get('account_no_masked')}. Window {window['start'][:10]} to {window['end'][:10]}.\n"
            f"Policy result (final, do not change): disposition {disp}, score {policy['score']:.0f}/100, reasons: {'; '.join(policy['reasons'])}.\n"
            f"Typologies: {', '.join(t['label'] for t in policy.get('typologies', [])) or 'none'}.\n"
            f"Proposed actions: {', '.join(a['type'] for a in actions) or 'none'}.\n"
            f"Evidence ledger:\n{_evidence_block(evidence)}\n\n"
            + (f"An STR draft is required. Use exactly these str_sections names: {', '.join(self._sections)}.\n" if disp == "str_draft" else "Set str_sections to null.\n")
            + ("Write a neutral customer_query letter asking about the source and purpose of the payments.\n" if disp == "escalate" else "Set customer_query to null.\n")
            + (f"Fix these reviewer issues from the previous draft: {'; '.join(issues)}\n" if issues else "")
        )
        try:
            out, call = await self._client.structured(self._route, self.prompt_version, self._system, user, NarrativeOutput)
        except LLMUnavailable as exc:
            return base, {**meta, "fallback_reason": fallback_reason(exc), "summary": f"fallback ({type(exc).__name__}): {meta['summary']}"}
        report = self._assemble(out, base, {e["id"] for e in evidence}, disp)
        live = {**call.as_meta(), "fallback_used": False, "summary": f"{len(report['citations'])} citations, {disp}"}
        return report, live

    def _assemble(self, out: NarrativeOutput, base: dict[str, Any], valid: set[str], disp: str) -> dict[str, Any]:
        summary, profile, flow = _render(out.executive_summary, valid), _render(out.profile_findings, valid), _render(out.flow_findings, valid)
        head, _, tail = base["summary_md"].partition(RISK_SECTION)
        if summary:
            head = "\n".join(["## Executive summary", *summary, "", "## Findings", "### Profile vs behaviour", *(profile or ["(see evidence list)"]), "### Flow pattern", *(flow or ["(see evidence list)"]), ""])
        summary_md = f"{head}{RISK_SECTION}{tail}"

        str_md = base["str_narrative_md"]
        if disp == "str_draft" and out.str_sections:
            lines = []
            for name in self._sections:
                s = out.str_sections.get(name)
                rendered = _render([s], valid) if s else []
                if not rendered:
                    lines = []
                    break
                lines.append(f"**{name}:** {rendered[0]}")
            if lines:
                str_md = "\n".join(["## STR narrative (draft for maker-checker review)", *lines])

        customer_md = base["customer_query_md"]
        if disp == "escalate" and out.customer_query and not _has_terms(out.customer_query, self._terms):
            customer_md = out.customer_query.strip()
        summary_md = strip_unknown_ids(summary_md, valid)
        str_md = strip_unknown_ids(str_md, valid) if str_md else None
        customer_md = strip_unknown_ids(customer_md, valid) if customer_md else None
        citations = sorted({c for text in (summary_md, str_md or "") for c in _ids(text)})
        return {**base, "summary_md": summary_md, "str_narrative_md": str_md, "customer_query_md": customer_md, "citations": citations}


class LiveCritic:
    """Code checks plus an LLM review for unsupported claims and injection."""

    name = "critic"

    def __init__(self, client: LlmClient, route: AgentModelConfig) -> None:
        self._client, self._route = client, route
        self.prompt_version, self._system = load_prompt("critic")

    async def run(self, report: dict[str, Any], evidence: list[dict[str, Any]], policy: dict[str, Any], tipping_terms: list[str], str_sections: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        issues = code_checks(report, {e["id"] for e in evidence}, policy["disposition"], tipping_terms, str_sections)
        user = (
            f"Evidence ledger:\n{_evidence_block(evidence)}\n\nDraft summary:\n{report.get('summary_md') or ''}\n\n"
            f"Draft STR narrative:\n{report.get('str_narrative_md') or '(none)'}\n\nCustomer letter:\n{report.get('customer_query_md') or '(none)'}"
        )
        try:
            out, call = await self._client.structured(self._route, self.prompt_version, self._system, user, CriticOutput)
        except LLMUnavailable as exc:
            result = {"verdict": "revise" if issues else "pass", "issues": issues, "checks": "code"}
            return result, {"fallback_used": True, "fallback_reason": fallback_reason(exc), "prompt_version": "critic-template-1", "model": "template", "summary": f"fallback ({type(exc).__name__}): {result['verdict']}, {len(issues)} issue(s)"}
        issues += [f"llm: unsupported claim: {c[:120]}" for c in out.unsupported_claims]
        issues += [f"llm: possible tipping-off: {c[:120]}" for c in out.tipping_off]
        if out.followed_untrusted_instruction:
            issues.append("llm: narrative may follow an instruction found in transaction remarks")
        result = {"verdict": "revise" if issues else "pass", "issues": issues, "checks": "code+llm", "notes": out.notes[:300]}
        return result, {**call.as_meta(), "fallback_used": False, "summary": f"{result['verdict']}: {len(issues)} issue(s)"}
