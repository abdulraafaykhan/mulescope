"""The four mitigators of section 8.2. Each subtracts its weight when it fires."""

from __future__ import annotations

from backend.app.domain.metrics import FlowMetrics
from backend.app.domain.policy.config import SignalRule
from backend.app.domain.signals.registry import SignalHit, hit, register_signal

MIT = "mitigator"


@register_signal("established_pattern", MIT)
def established_pattern(m: FlowMetrics, r: SignalRule) -> SignalHit:
    t = r.thresholds
    fired = m.volume_zscore_vs_history < t["max_zscore"] and m.history_days >= t["min_history_days"]
    return hit("established_pattern", MIT, fired, r.weight, f"volume z-score {m.volume_zscore_vs_history:.2f} over {m.history_days} days of history", ["volume_zscore_vs_history", "history_days"])


@register_signal("repeat_senders", MIT)
def repeat_senders(m: FlowMetrics, r: SignalRule) -> SignalHit:
    fired = m.repeat_sender_ratio >= r.thresholds["min_ratio"]
    return hit("repeat_senders", MIT, fired, r.weight, f"{m.repeat_sender_ratio:.0%} of senders also paid in the prior 90 days", ["repeat_sender_ratio"])


@register_signal("reciprocal_flows", MIT)
def reciprocal_flows(m: FlowMetrics, r: SignalRule) -> SignalHit:
    fired = m.reciprocal_flow_share >= r.thresholds["min_share"]
    return hit("reciprocal_flows", MIT, fired, r.weight, f"{m.reciprocal_flow_share:.0%} of outflow returned to senders", ["reciprocal_flow_share"])


@register_signal("consistent_business_profile", MIT)
def consistent_business_profile(m: FlowMetrics, r: SignalRule) -> SignalHit:
    fired = m.business_occupation and m.turnover_multiple < r.thresholds["max_turnover_multiple"]
    return hit("consistent_business_profile", MIT, fired, r.weight, f"business occupation, turnover {m.turnover_multiple:.1f}x declared", ["turnover_multiple"])
