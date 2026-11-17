"""Action planner: playbook lookup from disposition and signals (section 8.4).

Pure: returns proposed actions; persistence and mock execution live in the
graph's ``plan_actions`` and ``execute_actions`` nodes. Each action carries
an idempotency key ``case_id:type:target``.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.app.domain.policy.config import PlaybookConfig
from backend.app.domain.policy.disposition import PolicyResult


class PlanContext(BaseModel):
    """Facts the playbook rules can test besides the policy result."""

    case_id: str
    account_id: str
    inflow_total: float
    stale_kyc: bool
    linked_accounts: list[str]


class ProposedAction(BaseModel):
    """An action proposed for analyst approval."""

    type: str
    target: str
    owner_role: str
    due_in_days: int
    requires_approval: bool
    reversible: bool
    mock_tool: str
    params: dict[str, object]
    description: str
    rule: str
    idempotency_key: str


def plan(policy: PolicyResult, ctx: PlanContext, playbook: PlaybookConfig) -> list[ProposedAction]:
    """Return the actions every matching rule proposes, deduplicated by type."""
    fired = set(policy.fired_signals)
    out: dict[str, ProposedAction] = {}
    for rule in playbook.rules:
        if rule.disposition and rule.disposition != policy.disposition.value:
            continue
        if rule.signals_any and not fired.intersection(rule.signals_any):
            continue
        if rule.min_score is not None and policy.score < rule.min_score:
            continue
        if rule.min_amount is not None and ctx.inflow_total < rule.min_amount:
            continue
        if rule.stale_kyc is not None and rule.stale_kyc != ctx.stale_kyc:
            continue
        if rule.linked_accounts and not ctx.linked_accounts:
            continue
        for name in rule.actions:
            if name in out:
                continue
            spec = playbook.actions[name]
            target = ",".join(ctx.linked_accounts) if name == "flag_linked_accounts" else ctx.account_id
            params: dict[str, object] = dict(spec.params)
            if name == "create_str_draft":
                params["str_due_days"] = playbook.str_due_days
            out[name] = ProposedAction(
                type=spec.type, target=target, owner_role=spec.owner_role, due_in_days=spec.due_in_days,
                requires_approval=spec.requires_approval, reversible=spec.reversible, mock_tool=spec.mock_tool,
                params=params, description=spec.description, rule=rule.name,
                idempotency_key=f"{ctx.case_id}:{spec.type}:{target}",
            )
    return list(out.values())
