"""Disposition policy (section 8.3). The only place a disposition is decided.

1. Score below ``close_below``: CLOSE.
2. Score from ``close_below`` to below ``str_at``: ESCALATE.
3. Score at or above ``str_at`` with at least ``str_min_signals`` risk signals
   and one of ``str_required_any``: STR_DRAFT (otherwise ESCALATE).
4. Within ``caution_band`` below a threshold, take the more cautious outcome:
   CLOSE becomes ESCALATE, and ESCALATE becomes STR_DRAFT when the STR
   conditions already hold.
5. Hard floor: victim-linked with ``hard_floor_victim_senders`` or more
   senders is never below ESCALATE.
"""

from __future__ import annotations

from pydantic import BaseModel

from backend.app.domain.enums import Disposition
from backend.app.domain.metrics import FlowMetrics
from backend.app.domain.policy.config import ScoringConfig
from backend.app.domain.policy.scoring import ScoreResult
from backend.app.domain.policy.typology import Typology, typologies


class PolicyResult(BaseModel):
    """Disposition plus everything needed to explain it."""

    disposition: Disposition
    score: float
    risk_points: float
    mitigation_points: float
    fired_signals: list[str]
    mitigators: list[str]
    reasons: list[str]
    typologies: list[Typology]
    policy_version: str
    breakdown: list[dict[str, object]]


def decide(result: ScoreResult, metrics: FlowMetrics, cfg: ScoringConfig) -> PolicyResult:
    """Apply the policy to a score."""
    d = cfg.disposition
    s = result.score
    fired = result.fired
    reasons: list[str] = []
    str_conditions = len(fired) >= d.str_min_signals and any(x in fired for x in d.str_required_any)

    if s < d.close_below:
        disposition = Disposition.CLOSE
        reasons.append(f"score {s:.0f} below {d.close_below:.0f}")
        if s >= d.close_below - d.caution_band:
            disposition = Disposition.ESCALATE
            reasons.append(f"within {d.caution_band:.0f} points of the escalate threshold: cautious outcome")
    elif s < d.str_at:
        disposition = Disposition.ESCALATE
        reasons.append(f"score {s:.0f} between {d.close_below:.0f} and {d.str_at:.0f}")
        if s >= d.str_at - d.caution_band and str_conditions:
            disposition = Disposition.STR_DRAFT
            reasons.append(f"within {d.caution_band:.0f} points of the STR threshold with STR conditions met: cautious outcome")
    elif str_conditions:
        disposition = Disposition.STR_DRAFT
        reasons.append(f"score {s:.0f} at or above {d.str_at:.0f} with {len(fired)} risk signals including {', '.join(x for x in d.str_required_any if x in fired)}")
    else:
        disposition = Disposition.ESCALATE
        reasons.append(f"score {s:.0f} is high but STR conditions are not met")

    if metrics.complaint_linked_senders >= d.hard_floor_victim_senders and disposition is Disposition.CLOSE:
        disposition = Disposition.ESCALATE
        reasons.append("hard floor: three or more senders have open fraud complaints")

    return PolicyResult(
        disposition=disposition,
        score=round(s, 1),
        risk_points=result.risk_points,
        mitigation_points=result.mitigation_points,
        fired_signals=fired,
        mitigators=result.mitigators,
        reasons=reasons,
        typologies=typologies(fired, cfg),
        policy_version=cfg.policy_version,
        breakdown=[h.model_dump() for h in result.hits],
    )
