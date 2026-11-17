"""The nine risk signals of section 8.2. Thresholds come from the rule."""

from __future__ import annotations

from backend.app.domain.metrics import FlowMetrics
from backend.app.domain.policy.config import SignalRule
from backend.app.domain.signals.registry import SignalHit, hit, register_signal

RISK = "risk"


@register_signal("fan_in")
def fan_in(m: FlowMetrics, r: SignalRule) -> SignalHit:
    t = r.thresholds
    fired = m.fan_in_count >= t["min_count"] and m.unrelated_sender_ratio >= t["min_unrelated_ratio"]
    return hit("fan_in", RISK, fired, r.weight, f"{m.fan_in_count} senders, {m.unrelated_sender_ratio:.0%} with no prior relationship", ["fan_in_count", "unrelated_sender_ratio"])


@register_signal("fast_exit")
def fast_exit(m: FlowMetrics, r: SignalRule) -> SignalHit:
    t = r.thresholds
    fired = m.median_exit_minutes < t["max_median_exit_minutes"] and m.pass_through_ratio >= t["min_pass_through"]
    return hit("fast_exit", RISK, fired, r.weight, f"median exit {m.median_exit_minutes:.0f} min, {m.pass_through_ratio:.0%} out within 24h", ["median_exit_minutes", "pass_through_ratio"])


@register_signal("low_retention")
def low_retention(m: FlowMetrics, r: SignalRule) -> SignalHit:
    fired = m.retention_ratio <= r.thresholds["max_retention_ratio"]
    return hit("low_retention", RISK, fired, r.weight, f"retention ratio {m.retention_ratio:.3f}", ["retention_ratio", "median_eod_balance"])


@register_signal("profile_mismatch")
def profile_mismatch(m: FlowMetrics, r: SignalRule) -> SignalHit:
    fired = m.turnover_multiple >= r.thresholds["min_turnover_multiple"]
    return hit("profile_mismatch", RISK, fired, r.weight, f"turnover {m.turnover_multiple:.1f}x declared", ["turnover_multiple", "declared_monthly_turnover"])


@register_signal("dormant_or_new")
def dormant_or_new(m: FlowMetrics, r: SignalRule) -> SignalHit:
    t = r.thresholds
    fired = m.account_age_days < t["max_age_days"] or m.dormancy_days > t["min_dormancy_days"]
    return hit("dormant_or_new", RISK, fired, r.weight, f"account age {m.account_age_days} days, dormant {m.dormancy_days} days before window", ["account_age_days", "dormancy_days"])


@register_signal("consolidation")
def consolidation(m: FlowMetrics, r: SignalRule) -> SignalHit:
    fired = m.outflow_total > 0 and m.beneficiary_concentration >= r.thresholds["min_concentration"]
    return hit("consolidation", RISK, fired, r.weight, f"top beneficiaries receive {m.beneficiary_concentration:.0%} of outflow", ["beneficiary_concentration"])


@register_signal("cashout_channel")
def cashout_channel(m: FlowMetrics, r: SignalRule) -> SignalHit:
    fired = m.cashout_share >= r.thresholds["min_cashout_share"]
    return hit("cashout_channel", RISK, fired, r.weight, f"{m.cashout_share:.0%} of outflow via ATM or wallet", ["cashout_share"])


@register_signal("victim_linked")
def victim_linked(m: FlowMetrics, r: SignalRule) -> SignalHit:
    t = r.thresholds
    n = m.complaint_linked_senders
    points = r.weight if n >= t["many_senders"] else t["one_sender_points"]
    return hit("victim_linked", RISK, n > 0, points, f"{n} sender(s) with open fraud complaints", ["complaint_linked_senders"])


@register_signal("structured_amounts")
def structured_amounts(m: FlowMetrics, r: SignalRule) -> SignalHit:
    fired = m.structured_amount_share >= r.thresholds["min_share"]
    return hit("structured_amounts", RISK, fired, r.weight, f"{m.structured_amount_share:.0%} of credits round or just under a limit", ["structured_amount_share"])
