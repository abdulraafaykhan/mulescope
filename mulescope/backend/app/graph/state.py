"""``CaseState``: the single LangGraph state for one case run (section 7).

Nodes return partial updates only. Lists written by the parallel Profiler and
Flow Analyst branches use reducers (``facts`` appends, ``findings`` and
``loop_counts`` merge). Values are JSON-friendly (ISO strings, floats) so the
MongoDB checkpointer can store them.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any]:
    """Reducer: shallow dict merge, right wins."""
    return {**(a or {}), **(b or {})}


class CaseState(TypedDict, total=False):
    """State carried through the investigation graph."""

    case_id: str
    run_id: str
    llm_mode: str
    alert: dict[str, Any]
    account: dict[str, Any]
    customer: dict[str, Any]
    window: dict[str, str]
    metrics: dict[str, Any]
    facts: Annotated[list[dict[str, Any]], operator.add]
    findings: Annotated[dict[str, Any], merge]
    evidence: list[dict[str, Any]]
    gaps: list[str]
    loop_counts: Annotated[dict[str, int], merge]
    policy: dict[str, Any]
    typologies: list[dict[str, Any]]
    proposed_actions: list[dict[str, Any]]
    report: dict[str, Any]
    critic_result: dict[str, Any]
    analyst_decision: dict[str, Any]
    final_disposition: str | None
    errors: Annotated[list[str], operator.add]
