"""``cases`` collection: the investigation lifecycle, one case per alert."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.convert import plain


class MongoCaseRepository:
    """Reads and updates cases."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.CASES]

    async def insert_many(self, docs: list[dict[str, Any]]) -> None:
        if docs:
            await self._col.insert_many(docs, ordered=False)

    async def get(self, case_id: str) -> dict[str, Any] | None:
        return plain(await self._col.find_one({"_id": case_id}))

    async def list(self, status: str | None = None, priority: int | None = None, limit: int = 500) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if priority:
            query["priority"] = priority
        cursor = self._col.find(query).sort([("priority", 1), ("sla_due_at", 1)]).limit(limit)
        return [plain(d) async for d in cursor]  # type: ignore[misc]

    async def update(self, case_id: str, fields: dict[str, Any], now: datetime) -> None:
        await self._col.update_one({"_id": case_id}, {"$set": {**fields, "updated_at": now}})

    async def count_by_status(self) -> dict[str, int]:
        cursor = await self._col.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])
        return {d["_id"]: d["n"] async for d in cursor}  # type: ignore[misc]
