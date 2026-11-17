"""Read-only tools the Flow Analyst can call (section 7).

``get_counterparties``, ``get_flow_path``, ``get_sender_overlap`` and
``check_complaints``. They sit on narrow query ports: no raw database handle,
no access to the truth database. Each returns a small JSON-friendly dict.
Remarks are never returned here; they stay inside ``<untrusted_data>``
blocks built by the prompt layer.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Protocol

from backend.app.services.metrics_service import party_key

MAX_ITEMS = 10


class ToolTxPort(Protocol):
    async def ledger(self, account_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]: ...
    async def by_senders(self, sender_refs: list[str], start: datetime, end: datetime) -> list[dict[str, Any]]: ...


class ToolComplaintPort(Protocol):
    async def for_beneficiary(self, account_id: str) -> list[dict[str, Any]]: ...


class FlowTools:
    """Bound to one case window; every method is read-only."""

    def __init__(self, tx: ToolTxPort, complaints: ToolComplaintPort, account_id: str, start: datetime, end: datetime) -> None:
        self._tx, self._complaints = tx, complaints
        self.account_id, self.start, self.end = account_id, start, end
        self._rows: list[dict[str, Any]] | None = None

    async def _window(self) -> list[dict[str, Any]]:
        if self._rows is None:
            self._rows = await self._tx.ledger(self.account_id, self.start, self.end)
        return self._rows

    async def credit_remarks(self) -> list[str]:
        """Remarks of window credits. Untrusted: only for code checks and <untrusted_data> blocks."""
        return [str(r["remarks"]) for r in await self._window() if r["direction"] == "credit" and r.get("remarks")]

    async def get_counterparties(self) -> dict[str, Any]:
        """Top senders and receivers in the window, by amount."""
        senders: dict[str, dict[str, Any]] = defaultdict(lambda: {"amount": 0.0, "count": 0})
        receivers: dict[str, dict[str, Any]] = defaultdict(lambda: {"amount": 0.0, "count": 0})
        for r in await self._window():
            book = senders if r["direction"] == "credit" else receivers
            k = party_key(r)
            book[k]["amount"] += r["amount"]
            book[k]["count"] += 1
            book[k]["name"] = r["cp_name"]
            book[k]["type"] = r["cp_type"]

        def top(book: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
            items = sorted(book.items(), key=lambda kv: -kv[1]["amount"])[:MAX_ITEMS]
            return [{"ref": k, **v, "amount": round(v["amount"], 2)} for k, v in items]

        return {"senders": top(senders), "receivers": top(receivers), "sender_count": len(senders), "receiver_count": len(receivers)}

    async def get_flow_path(self) -> dict[str, Any]:
        """Internal accounts upstream or downstream of this account (layering)."""
        rows = await self._window()
        upstream = sorted({r["cp_ref"] for r in rows if r["cp_type"] == "account" and r["direction"] == "credit"})
        downstream = sorted({r["cp_ref"] for r in rows if r["cp_type"] == "account" and r["direction"] == "debit"})
        return {"upstream_internal": upstream[:MAX_ITEMS], "downstream_internal": downstream[:MAX_ITEMS], "linked_accounts": sorted(set(upstream) | set(downstream))}

    async def get_sender_overlap(self) -> dict[str, Any]:
        """Other accounts at our bank that the same senders paid in this window."""
        senders = sorted({r["cp_ref"] for r in await self._window() if r["direction"] == "credit" and r["cp_ref"]})
        overlap: dict[str, set[str]] = defaultdict(set)
        for r in await self._tx.by_senders(senders, self.start - timedelta(days=30), self.end):
            if r["account_id"] != self.account_id and r["direction"] == "credit":
                overlap[r["account_id"]].add(str(r["cp_ref"]))
        ranked = sorted(overlap.items(), key=lambda kv: -len(kv[1]))[:MAX_ITEMS]
        return {"accounts": [{"account_id": a, "shared_senders": len(s)} for a, s in ranked]}

    async def check_complaints(self) -> dict[str, Any]:
        """Open fraud complaints naming this account as beneficiary."""
        complaints = [c for c in await self._complaints.for_beneficiary(self.account_id) if c.get("status") == "open"]
        return {
            "count": len(complaints),
            "victims": sorted({c["victim_account_id"] for c in complaints}),
            "amount": round(sum(c.get("amount", 0.0) for c in complaints), 2),
            "complaint_ids": [c["id"] for c in complaints],
        }
