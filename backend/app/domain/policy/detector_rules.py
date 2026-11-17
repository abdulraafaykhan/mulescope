"""Pure detector rules (section 6.4) and alert priority.

``evaluate`` takes coarse window statistics for one account and returns the
rules that fired. Thresholds come only from ``DetectorConfig``.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.policy.config import DetectorConfig

RULE_FAN_IN = "PT-FANIN-01"
RULE_HIGH_VALUE = "PT-HIGHVALUE-01"
RULE_DORMANT = "PT-DORMANT-01"


@dataclass(frozen=True)
class WindowStats:
    """Coarse statistics the detector needs for one account."""

    account_id: str
    inflow: float
    outflow: float
    distinct_senders: int
    credits: int
    dormancy_days: int

    @property
    def pass_through(self) -> float:
        return min(self.outflow / self.inflow, 1.0) if self.inflow > 0 else 0.0


def evaluate(stats: WindowStats, cfg: DetectorConfig) -> list[str]:
    """Return the ids of the rules that fire for ``stats``."""
    r = cfg.rules
    fired: list[str] = []
    if stats.distinct_senders >= r.fan_in_pass_through.min_senders and stats.inflow >= r.fan_in_pass_through.min_inflow and stats.pass_through >= r.fan_in_pass_through.min_pass_through:
        fired.append(RULE_FAN_IN)
    if stats.inflow >= r.high_value_pass_through.min_inflow and stats.pass_through >= r.high_value_pass_through.min_pass_through:
        fired.append(RULE_HIGH_VALUE)
    if stats.dormancy_days >= r.dormant_reactivation.min_dormancy_days and stats.inflow >= r.dormant_reactivation.min_inflow:
        fired.append(RULE_DORMANT)
    return fired


def priority(stats: WindowStats, cfg: DetectorConfig) -> int:
    """1 (highest) to 3, from inflow and fan-in."""
    p = cfg.priority
    if stats.inflow >= p.high_inflow or stats.distinct_senders >= p.high_senders:
        return 1
    if stats.inflow >= p.medium_inflow:
        return 2
    return 3
