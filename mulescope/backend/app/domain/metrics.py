"""Flow metrics for one account and window (build prompt section 8.1).

Pure functions over ledger entries already fetched by the caller (one indexed
query per alert). No I/O, no framework imports. Called by the metrics service,
the ``compute_metrics`` graph node and ``uv run check-policy``.

Definitions that needed a concrete choice:

* ``median_exit_minutes``: for each credit, minutes until the cumulative
  outflow after it reaches ``exit_match_ratio`` of the credit (credits that
  never exit count as the rest of the window).
* ``pass_through_ratio``: sum over credits of ``min(credit, outflow within
  pass_through_hours after it)`` divided by total inflow.
* ``retention_ratio``: median end-of-day balance over the window divided by
  the median inflow of days that had inflow.
* ``history_days``: account age when the account had activity in the prior
  period, else 0.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import BaseModel

from backend.app.domain.policy.config import MetricsConfig

IST = timedelta(hours=5, minutes=30)
NO_HISTORY_ZSCORE = 99.0


@dataclass(frozen=True)
class Entry:
    """One ledger entry as the metrics need it."""

    ts: datetime
    direction: str
    amount: float
    channel: str
    party: str  # counterparty ref id, or a stable name key when there is none
    balance_after: float

    @property
    def is_credit(self) -> bool:
        return self.direction == "credit"


class FlowMetrics(BaseModel):
    """Every metric of section 8.1 plus the totals the narrative needs."""

    window_days: int
    inflow_total: float
    outflow_total: float
    credit_count: int
    debit_count: int
    fan_in_count: int
    unrelated_sender_ratio: float
    repeat_sender_ratio: float
    median_exit_minutes: float
    pass_through_ratio: float
    retention_ratio: float
    turnover_multiple: float
    declared_monthly_turnover: float
    account_age_days: int
    dormancy_days: int
    history_days: int
    cashout_share: float
    beneficiary_concentration: float
    top_beneficiaries: list[str]
    structured_amount_share: float
    volume_zscore_vs_history: float
    reciprocal_flow_share: float
    complaint_linked_senders: int
    business_occupation: bool
    median_eod_balance: float
    median_daily_inflow: float


def _ratio(num: float, den: float) -> float:
    return num / den if den > 0 else 0.0


def _exit_minutes(credits: list[Entry], debits: list[Entry], window_end: datetime, ratio: float) -> list[float]:
    out: list[float] = []
    for c in credits:
        need = c.amount * ratio
        acc = 0.0
        found = None
        for d in debits:
            if d.ts <= c.ts:
                continue
            acc += d.amount
            if acc >= need:
                found = d.ts
                break
        end = found or window_end
        out.append((end - c.ts).total_seconds() / 60.0)
    return out


def _pass_through(credits: list[Entry], debits: list[Entry], hours: int, inflow: float) -> float:
    span = timedelta(hours=hours)
    moved = 0.0
    for c in credits:
        out = sum(d.amount for d in debits if c.ts < d.ts <= c.ts + span)
        moved += min(c.amount, out)
    return _ratio(moved, inflow)


def _ist_day(ts: datetime) -> int:
    return (ts + IST).toordinal()


def _eod_and_daily(window: list[Entry], opening: float, start: datetime, days: int) -> tuple[list[float], list[float]]:
    by_day: dict[int, list[Entry]] = {}
    for e in window:
        by_day.setdefault(_ist_day(e.ts), []).append(e)
    first = _ist_day(start)
    balance = opening
    eod: list[float] = []
    daily_in: list[float] = []
    for d in range(first, first + days):
        entries = by_day.get(d, [])
        if entries:
            balance = entries[-1].balance_after
            inflow = sum(e.amount for e in entries if e.is_credit)
            if inflow > 0:
                daily_in.append(inflow)
        eod.append(balance)
    return eod, daily_in


def _is_structured(amount: float, cfg: MetricsConfig) -> bool:
    if amount > 0 and amount % cfg.round_amount == 0:
        return True
    return any(limit * (1 - cfg.structuring_margin) <= amount < limit for limit in cfg.structuring_limits)


def _zscore(prior_credits: list[Entry], window_inflow: float, window_start: datetime, window_days: int, history_days: int) -> float:
    weeks = max(history_days // 7, 1)
    buckets = [0.0] * weeks
    for e in prior_credits:
        age_days = (window_start - e.ts).total_seconds() / 86_400
        idx = int(age_days // 7)
        if 0 <= idx < weeks:
            buckets[idx] += e.amount
    weekly_now = window_inflow / (window_days / 7)
    mean = statistics.fmean(buckets)
    std = statistics.pstdev(buckets)
    if std == 0:
        return 0.0 if math.isclose(weekly_now, mean) else NO_HISTORY_ZSCORE
    return (weekly_now - mean) / std


def compute_metrics(
    *,
    window: list[Entry],
    prior: list[Entry],
    window_start: datetime,
    window_end: datetime,
    opened_at: datetime,
    last_activity_before: datetime | None,
    opening_balance: float,
    declared_monthly_turnover: float,
    occupation: str,
    complaint_victims: set[str],
    cfg: MetricsConfig,
) -> FlowMetrics:
    """Compute :class:`FlowMetrics` for one account window.

    Args:
        window: Entries in ``[window_start, window_end)``, oldest first.
        prior: Entries in the history period before the window, oldest first.
        window_start: Window start (UTC).
        window_end: Window end (UTC, exclusive).
        opened_at: Account opening time.
        last_activity_before: Latest entry before the window (any age), if any.
        opening_balance: Balance just before the window.
        declared_monthly_turnover: Declared turnover in INR per month.
        occupation: KYC occupation.
        complaint_victims: Counterparty ids of open complaints naming this account.
        cfg: Metric parameters from ``scoring.yaml``.

    Returns:
        The metrics.
    """
    days = max(round((window_end - window_start).total_seconds() / 86_400), 1)
    credits = [e for e in window if e.is_credit]
    debits = [e for e in window if not e.is_credit]
    inflow = sum(e.amount for e in credits)
    outflow = sum(e.amount for e in debits)

    senders = {e.party for e in credits}
    prior_parties = {e.party for e in prior}
    prior_payers = {e.party for e in prior if e.is_credit}
    unrelated = sum(1 for s in senders if s not in prior_parties)
    repeat = sum(1 for s in senders if s in prior_payers)

    exits = _exit_minutes(credits, debits, window_end, cfg.exit_match_ratio)
    eod, daily_in = _eod_and_daily(window, opening_balance, window_start, days)
    med_eod = statistics.median(eod) if eod else opening_balance
    med_in = statistics.median(daily_in) if daily_in else 0.0

    bene = Counter[str]()
    for d in debits:
        bene[d.party] += d.amount
    top = bene.most_common(cfg.top_beneficiaries)
    cash = sum(d.amount for d in debits if d.channel in cfg.cash_like_channels)
    reciprocal = sum(d.amount for d in debits if d.party in senders)

    age = max((window_start - opened_at).days, 0)
    dormancy = (window_start - last_activity_before).days if last_activity_before else age
    history = age if prior else 0
    monthly_equiv = inflow * 30 / days
    occ = occupation.lower()

    return FlowMetrics(
        window_days=days,
        inflow_total=round(inflow, 2),
        outflow_total=round(outflow, 2),
        credit_count=len(credits),
        debit_count=len(debits),
        fan_in_count=len(senders),
        unrelated_sender_ratio=round(_ratio(unrelated, len(senders)), 4),
        repeat_sender_ratio=round(_ratio(repeat, len(senders)), 4),
        median_exit_minutes=round(statistics.median(exits), 1) if exits else float(days * 1440),
        pass_through_ratio=round(_pass_through(credits, debits, cfg.pass_through_hours, inflow), 4),
        retention_ratio=round(_ratio(med_eod, med_in), 4) if med_in else 1.0,
        turnover_multiple=round(_ratio(monthly_equiv, declared_monthly_turnover) if declared_monthly_turnover else monthly_equiv / 1000, 2),
        declared_monthly_turnover=declared_monthly_turnover,
        account_age_days=age,
        dormancy_days=max(dormancy, 0),
        history_days=history,
        cashout_share=round(_ratio(cash, outflow), 4),
        beneficiary_concentration=round(_ratio(sum(v for _, v in top), outflow), 4),
        top_beneficiaries=[k for k, _ in top],
        structured_amount_share=round(_ratio(sum(1 for c in credits if _is_structured(c.amount, cfg)), len(credits)), 4),
        volume_zscore_vs_history=round(_zscore([e for e in prior if e.is_credit], inflow, window_start, days, cfg.history_days), 3),
        reciprocal_flow_share=round(_ratio(reciprocal, outflow), 4),
        complaint_linked_senders=len(senders & complaint_victims),
        business_occupation=any(k in occ for k in cfg.business_keywords),
        median_eod_balance=round(med_eod, 2),
        median_daily_inflow=round(med_in, 2),
    )
