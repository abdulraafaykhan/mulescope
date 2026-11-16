"""PassThroughDetector: scans the 14-day window and opens alerts and cases.

Called by ``uv run seed`` after loading data and by ``POST /api/v1/alerts/detect``.
It reads two queries (window rows and last activity before the window),
evaluates the pure rules in ``domain/policy/detector_rules.py`` and writes one
alert plus one case per firing account. ``dedupe_key = account_id + window
start`` keeps reruns idempotent.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from backend.app.core.clock import Clock
from backend.app.domain.enums import AlertStatus, CaseStatus
from backend.app.domain.policy.config import PlaybookConfig, ScoringConfig
from backend.app.domain.policy.detector_rules import WindowStats, evaluate, priority

DAY_SECONDS = 86_400
IST_OFFSET = timedelta(hours=5, minutes=30)


def dataset_window_end(as_of: date) -> datetime:
    """Exclusive end of the dataset: ``as_of`` + 1 day at 00:00 IST, in UTC."""
    nxt = as_of + timedelta(days=1)
    return datetime(nxt.year, nxt.month, nxt.day, tzinfo=UTC) - IST_OFFSET


class TransactionScanPort(Protocol):
    async def window_rows(self, start: datetime, end: datetime) -> list[dict[str, Any]]: ...
    async def last_activity_before(self, ts: datetime) -> dict[str, datetime]: ...


class AlertWritePort(Protocol):
    async def dedupe_keys(self) -> set[str]: ...
    async def count(self) -> int: ...
    async def insert_many(self, docs: list[dict[str, Any]]) -> None: ...


class CaseWritePort(Protocol):
    async def insert_many(self, docs: list[dict[str, Any]]) -> None: ...


@dataclass
class DetectionResult:
    """Outcome of one scan."""

    window_start: datetime
    window_end: datetime
    scanned_accounts: int
    alerts_created: list[dict[str, Any]] = field(default_factory=list)
    skipped_existing: int = 0


class PassThroughDetector:
    """Rules-based detector for rapid pass-through activity."""

    def __init__(self, tx: TransactionScanPort, alerts: AlertWritePort, cases: CaseWritePort, scoring: ScoringConfig, playbook: PlaybookConfig, clock: Clock) -> None:
        self._tx, self._alerts, self._cases = tx, alerts, cases
        self._cfg = scoring.detector
        self._playbook = playbook
        self._clock = clock

    async def detect(self, window_end: datetime) -> DetectionResult:
        """Scan the window ending at ``window_end`` and create alerts and cases."""
        start = window_end - timedelta(days=self._cfg.window_days)
        rows = await self._tx.window_rows(start, window_end)
        last = await self._tx.last_activity_before(start)
        stats = _aggregate(rows, last, start)
        result = DetectionResult(start, window_end, len(stats))

        existing = await self._alerts.dedupe_keys()
        candidates: list[tuple[WindowStats, list[str]]] = []
        for s in stats:
            fired = evaluate(s, self._cfg)
            if fired:
                candidates.append((s, fired))
        candidates.sort(key=lambda c: (priority(c[0], self._cfg), c[0].account_id))

        now = self._clock.now()
        seq = await self._alerts.count()
        alerts: list[dict[str, Any]] = []
        cases: list[dict[str, Any]] = []
        for s, fired in candidates:
            key = f"{s.account_id}:{start.date().isoformat()}"
            if key in existing:
                result.skipped_existing += 1
                continue
            seq += 1
            prio = priority(s, self._cfg)
            alert_id, case_id = f"ALT-{seq:04d}", f"CASE-{seq:04d}"
            alerts.append({
                "_id": alert_id, "account_id": s.account_id, "rule_id": fired[0], "rule_version": self._cfg.rule_version,
                "window": {"start": start, "end": window_end},
                "trigger_metrics": {"inflow": round(s.inflow, 2), "outflow": round(s.outflow, 2), "pass_through": round(s.pass_through, 3), "distinct_senders": s.distinct_senders, "credits": s.credits, "dormancy_days": s.dormancy_days, "rules_fired": fired},
                "priority": prio, "status": AlertStatus.IN_CASE.value, "dedupe_key": key,
                "created_at": now, "updated_at": now, "schema_version": 1,
            })
            sla_days = self._playbook.sla_days_by_priority.get(prio, max(self._playbook.sla_days_by_priority.values()))
            cases.append({
                "_id": case_id, "alert_id": alert_id, "account_id": s.account_id, "status": CaseStatus.NEW.value, "priority": prio,
                "assigned_to": None, "sla_due_at": now + timedelta(days=sla_days), "score": None, "recommended_disposition": None,
                "final_disposition": None, "current_run_id": None, "created_at": now, "updated_at": now, "schema_version": 1,
            })
        await self._alerts.insert_many(alerts)
        await self._cases.insert_many(cases)
        result.alerts_created = alerts
        return result


def _aggregate(rows: list[dict[str, Any]], last: dict[str, datetime], start: datetime) -> list[WindowStats]:
    inflow: dict[str, float] = defaultdict(float)
    outflow: dict[str, float] = defaultdict(float)
    senders: dict[str, set[str]] = defaultdict(set)
    credits: dict[str, int] = defaultdict(int)
    for r in rows:
        acct = r["account_id"]
        if r["direction"] == "credit":
            inflow[acct] += r["amount"]
            credits[acct] += 1
            if r["cp_ref"]:
                senders[acct].add(r["cp_ref"])
        else:
            outflow[acct] += r["amount"]
    out = []
    for acct in sorted(set(inflow) | set(outflow)):
        prev = last.get(acct)
        dormancy = int((start - prev).total_seconds() // DAY_SECONDS) if prev else 0
        out.append(WindowStats(acct, inflow[acct], outflow[acct], len(senders[acct]), credits[acct], dormancy))
    return out
