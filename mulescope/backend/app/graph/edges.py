"""Conditional edges with loop caps (section 7)."""

from __future__ import annotations

from backend.app.graph.state import CaseState

MAX_SUFFICIENCY_LOOPS = 1
MAX_CRITIC_LOOPS = 1
MAX_REQUEST_MORE_LOOPS = 1


def after_sufficiency(state: CaseState) -> str:
    """Back to the Flow Analyst when evidence is missing (max 1 loop)."""
    if state.get("gaps") and state.get("loop_counts", {}).get("sufficiency", 0) <= MAX_SUFFICIENCY_LOOPS:
        return "flow_analyst"
    return "score_and_policy"


def after_critic(state: CaseState) -> str:
    """Back to the Narrative Writer when the critic found issues (max 1 loop)."""
    verdict = (state.get("critic_result") or {}).get("verdict")
    if verdict != "pass" and state.get("loop_counts", {}).get("critic", 0) <= MAX_CRITIC_LOOPS:
        return "narrative_writer"
    return "analyst_gate"


def after_decision(state: CaseState) -> str:
    """Route the analyst's decision."""
    kind = (state.get("analyst_decision") or {}).get("decision")
    if kind == "request_more" and state.get("loop_counts", {}).get("request_more", 0) <= MAX_REQUEST_MORE_LOOPS:
        return "flow_analyst"
    if kind in ("reject", "request_more"):
        return "finalize"
    return "execute_actions"
