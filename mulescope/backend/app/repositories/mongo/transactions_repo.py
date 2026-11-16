"""Read-only access to the ``transactions`` ledger (the TransactionQueryPort).

Every query starts with ``$match``/filters on indexed fields: ``(account_id,
ts)`` for an account's ledger and ``(counterparty.ref_id, ts)`` for sender
lookups. Returns plain dicts with float rupees. Used by the detector, the
metrics node, agent tools and the case-data API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.convert import to_float, utc

LEDGER_PROJECTION = {
    "transfer_id": 1, "account_id": 1, "direction": 1, "amount": 1, "channel": 1, "ts": 1,
    "counterparty": 1, "remarks": 1, "balance_after": 1,
}


def _row(doc: dict[str, Any]) -> dict[str, Any]:
    cp = doc.get("counterparty") or {}
    return {
        "id": str(doc["_id"]),
        "transfer_id": doc.get("transfer_id"),
        "account_id": doc.get("account_id"),
        "direction": doc.get("direction"),
        "amount": to_float(doc.get("amount")),
        "channel": doc.get("channel"),
        "ts": utc(doc.get("ts")),
        "cp_type": cp.get("type"),
        "cp_ref": cp.get("ref_id"),
        "cp_name": cp.get("name"),
        "remarks": doc.get("remarks"),
        "balance_after": to_float(doc.get("balance_after")),
    }


class MongoTransactionRepository:
    """Queries over ledger entries. Never writes."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.TRANSACTIONS]

    async def ledger(self, account_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """All entries of one account in ``[start, end)``, oldest first."""
        cursor = self._col.find({"account_id": account_id, "ts": {"$gte": start, "$lt": end}}, LEDGER_PROJECTION).sort([("ts", 1), ("_id", 1)])
        return [_row(d) async for d in cursor]

    async def last_before(self, account_id: str, ts: datetime) -> dict[str, Any] | None:
        """The latest entry of an account strictly before ``ts``."""
        doc = await self._col.find_one({"account_id": account_id, "ts": {"$lt": ts}}, LEDGER_PROJECTION, sort=[("ts", -1)])
        return _row(doc) if doc else None

    async def window_rows(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Compact rows of every account in a window (detector scan)."""
        cursor = self._col.find({"ts": {"$gte": start, "$lt": end}}, {"account_id": 1, "direction": 1, "amount": 1, "counterparty.ref_id": 1, "ts": 1})
        out = []
        async for d in cursor:
            out.append({"account_id": d["account_id"], "direction": d["direction"], "amount": to_float(d["amount"]), "cp_ref": (d.get("counterparty") or {}).get("ref_id")})
        return out

    async def last_activity_before(self, ts: datetime) -> dict[str, datetime]:
        """Account -> latest entry time before ``ts`` (one aggregation)."""
        pipeline = [{"$match": {"ts": {"$lt": ts}}}, {"$group": {"_id": "$account_id", "last": {"$max": "$ts"}}}]
        cursor = await self._col.aggregate(pipeline)
        return {d["_id"]: utc(d["last"]) async for d in cursor}  # type: ignore[misc]

    async def page(self, account_id: str, start: datetime, end: datetime, cursor: str | None, limit: int) -> tuple[list[dict[str, Any]], str | None]:
        """Newest-first page of an account's entries; cursor is the last ``_id``."""
        query: dict[str, Any] = {"account_id": account_id, "ts": {"$gte": start, "$lt": end}}
        if cursor:
            query["_id"] = {"$lt": ObjectId(cursor)}
        docs = [d async for d in self._col.find(query, LEDGER_PROJECTION).sort([("ts", -1), ("_id", -1)]).limit(limit + 1)]
        nxt = str(docs[limit - 1]["_id"]) if len(docs) > limit else None
        return [_row(d) for d in docs[:limit]], nxt

    async def by_sender(self, sender_ref: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Entries where ``sender_ref`` is the counterparty (sender overlap tool)."""
        cursor = self._col.find({"counterparty.ref_id": sender_ref, "ts": {"$gte": start, "$lt": end}}, LEDGER_PROJECTION)
        return [_row(d) async for d in cursor]
