"""``alerts`` collection: detector output, one document per account window.

``dedupe_key`` (unique index) makes detection reruns idempotent.
"""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.convert import plain


class MongoAlertRepository:
    """Reads and writes alerts."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.ALERTS]

    async def dedupe_keys(self) -> set[str]:
        return {d["dedupe_key"] async for d in self._col.find({}, {"dedupe_key": 1})}

    async def count(self) -> int:
        return await self._col.count_documents({})

    async def insert_many(self, docs: list[dict[str, Any]]) -> None:
        if docs:
            await self._col.insert_many(docs, ordered=False)

    async def get(self, alert_id: str) -> dict[str, Any] | None:
        return plain(await self._col.find_one({"_id": alert_id}))

    async def list(self, status: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        query = {"status": status} if status else {}
        cursor = self._col.find(query).sort([("status", 1), ("priority", 1)]).limit(limit)
        return [plain(d) async for d in cursor]  # type: ignore[misc]

    async def account_ids(self) -> list[str]:
        return [d["account_id"] async for d in self._col.find({}, {"account_id": 1})]
