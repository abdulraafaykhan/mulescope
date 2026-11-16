"""``audit_logs``: append-only, tamper-evident event stream (the AuditSink).

Each record stores ``prev_hash`` and a SHA-256 ``hash`` of its own content,
chained per case. A per-case lock keeps parallel graph branches from forking
the chain (single API process). ``verify_chain`` recomputes every hash.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.convert import plain, utc

GENESIS = "0" * 64


def _digest(record: dict[str, Any]) -> str:
    body = {k: record.get(k) for k in ("ts", "actor", "event", "entity", "case_id", "run_id", "payload", "prev_hash")}
    body["ts"] = utc(body["ts"]).isoformat(timespec="milliseconds") if body["ts"] else None  # type: ignore[union-attr]
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


class MongoAuditRepository:
    """Appends and verifies audit records."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.AUDIT_LOGS]
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def append(self, *, ts: datetime, actor: dict[str, str], event: str, entity: dict[str, str], case_id: str | None, run_id: str | None, payload: dict[str, Any]) -> str:
        """Append one record to the case chain; returns its hash."""
        key = case_id or "_global"
        # JSON round-trip so the stored payload hashes the same after reading it back.
        payload = json.loads(json.dumps(payload, default=str))
        async with self._locks[key]:
            last = await self._col.find_one({"case_id": case_id}, {"hash": 1}, sort=[("ts", -1), ("_id", -1)])
            # Millisecond precision so the stored value hashes identically on read.
            ts = ts.replace(microsecond=ts.microsecond // 1000 * 1000)
            record = {"ts": ts, "actor": actor, "event": event, "entity": entity, "case_id": case_id, "run_id": run_id, "payload": payload, "prev_hash": last["hash"] if last else GENESIS}
            record["hash"] = _digest(record)
            record["created_at"] = ts
            await self._col.insert_one(dict(record))
            return str(record["hash"])

    async def list(self, case_id: str | None = None, event: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if case_id:
            query["case_id"] = case_id
        if event:
            query["event"] = {"$regex": f"^{event}"}
        cursor = self._col.find(query).sort([("ts", -1), ("_id", -1)]).limit(limit)
        return [plain(d) async for d in cursor]  # type: ignore[misc]

    async def verify_chain(self, case_id: str) -> dict[str, Any]:
        """Recompute the chain for a case; report the first broken record."""
        prev = GENESIS
        count = 0
        async for d in self._col.find({"case_id": case_id}).sort([("ts", 1), ("_id", 1)]):
            count += 1
            if d.get("prev_hash") != prev or _digest(d) != d.get("hash"):
                return {"case_id": case_id, "valid": False, "records": count, "broken_at": str(d["_id"])}
            prev = d["hash"]
        return {"case_id": case_id, "valid": True, "records": count, "head": prev}
