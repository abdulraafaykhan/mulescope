"""Builds the inputs for ``compute_metrics`` and runs it for one account window.

Queries: the account's ledger for the window plus the history period (one
indexed range query on ``(account_id, ts)``), the last entry before the
history, the account and customer, and complaints naming the account. Used
by the ``compute_metrics`` node and ``uv run check-policy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from backend.app.core.errors import NotFound
from backend.app.domain.metrics import Entry, FlowMetrics, compute_metrics
from backend.app.domain.policy.config import ScoringConfig


class LedgerPort(Protocol):
    async def ledger(self, account_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]: ...
    async def last_before(self, account_id: str, ts: datetime) -> dict[str, Any] | None: ...


class GetPort(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...


class ComplaintPort(Protocol):
    async def for_beneficiary(self, account_id: str) -> list[dict[str, Any]]: ...


def party_key(row: dict[str, Any]) -> str:
    """Stable key of a counterparty: ref id, else ``ATM``, else the name."""
    if row.get("cp_ref"):
        return str(row["cp_ref"])
    if row.get("cp_type") == "atm":
        return "ATM"
    return f"name:{row.get('cp_name')}"


def to_entry(row: dict[str, Any]) -> Entry:
    return Entry(ts=row["ts"], direction=row["direction"], amount=row["amount"], channel=row["channel"], party=party_key(row), balance_after=row["balance_after"])


@dataclass
class MetricsBundle:
    """Metrics plus the raw facts later nodes cite."""

    metrics: FlowMetrics
    account: dict[str, Any]
    customer: dict[str, Any]
    window_rows: list[dict[str, Any]]
    complaints: list[dict[str, Any]]


class MetricsService:
    """Computes flow metrics for an account and window."""

    def __init__(self, tx: LedgerPort, accounts: GetPort, customers: GetPort, complaints: ComplaintPort, scoring: ScoringConfig) -> None:
        self._tx, self._accounts, self._customers, self._complaints = tx, accounts, customers, complaints
        self._cfg = scoring

    async def compute(self, account_id: str, window_start: datetime, window_end: datetime) -> MetricsBundle:
        """Fetch everything for one account window and compute metrics."""
        account = await self._accounts.get(account_id)
        if account is None:
            raise NotFound(f"account {account_id} not found", detail={"account_id": account_id})
        customer = await self._customers.get(account["customer_id"]) or {}
        history_start = window_start - timedelta(days=self._cfg.metrics.history_days)
        rows = await self._tx.ledger(account_id, history_start, window_end)
        prior_rows = [r for r in rows if r["ts"] < window_start]
        window_rows = [r for r in rows if r["ts"] >= window_start]
        last_prior = prior_rows[-1] if prior_rows else await self._tx.last_before(account_id, window_start)
        if last_prior:
            opening = last_prior["balance_after"]
        elif window_rows:
            first = window_rows[0]
            opening = first["balance_after"] - (first["amount"] if first["direction"] == "credit" else -first["amount"])
        else:
            opening = account.get("balance", 0.0)
        complaints = [c for c in await self._complaints.for_beneficiary(account_id) if c.get("status") == "open"]
        kyc = customer.get("kyc", {})
        declared = account.get("declared_monthly_turnover") or (kyc.get("declared_income", 0.0) / 12)
        metrics = compute_metrics(
            window=[to_entry(r) for r in window_rows],
            prior=[to_entry(r) for r in prior_rows],
            window_start=window_start,
            window_end=window_end,
            opened_at=account["opened_at"],
            last_activity_before=last_prior["ts"] if last_prior else None,
            opening_balance=opening,
            declared_monthly_turnover=float(declared or 0.0),
            occupation=str(kyc.get("occupation", "")),
            complaint_victims={str(c["victim_account_id"]) for c in complaints},
            cfg=self._cfg.metrics,
        )
        return MetricsBundle(metrics, account, customer, window_rows, complaints)
