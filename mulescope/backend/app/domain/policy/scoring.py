"""Deterministic risk score: registered risk signals minus mitigators, floored at 0.

Only signals that have a rule in ``scoring.yaml`` are evaluated, so a signal
is switched on or off by configuration. Called by ``score_and_policy``.
"""

from __future__ import annotations

from pydantic import BaseModel

import backend.app.domain.signals  # noqa: F401  (registers every signal)
from backend.app.domain.metrics import FlowMetrics
from backend.app.domain.policy.config import ScoringConfig
from backend.app.domain.signals.registry import SignalHit, registered


class ScoreResult(BaseModel):
    """Score with its full breakdown."""

    score: float
    risk_points: float
    mitigation_points: float
    hits: list[SignalHit]

    @property
    def fired(self) -> list[str]:
        return [h.name for h in self.hits if h.kind == "risk" and h.fired]

    @property
    def mitigators(self) -> list[str]:
        return [h.name for h in self.hits if h.kind == "mitigator" and h.fired]


def score(metrics: FlowMetrics, cfg: ScoringConfig) -> ScoreResult:
    """Evaluate every configured signal and mitigator against ``metrics``."""
    hits: list[SignalHit] = []
    for sig in registered("risk"):
        if sig.name in cfg.signals:
            hits.append(sig.fn(metrics, cfg.signals[sig.name]))
    for sig in registered("mitigator"):
        if sig.name in cfg.mitigators:
            hits.append(sig.fn(metrics, cfg.mitigators[sig.name]))
    risk = sum(h.points for h in hits if h.kind == "risk")
    mitigation = sum(h.points for h in hits if h.kind == "mitigator")
    return ScoreResult(score=max(risk - mitigation, 0.0), risk_points=risk, mitigation_points=mitigation, hits=hits)
