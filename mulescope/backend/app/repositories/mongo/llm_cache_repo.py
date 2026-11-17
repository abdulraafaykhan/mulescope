"""``llm_cache``: cached LLM responses keyed by a hash of model, prompt version and input.

``_id`` is the key, so a lookup is a primary-key read. The collection has a
TTL index on ``created_at`` (``config/llm.yaml`` cache.ttl_days) created by
the bootstrap. Used only by ``llm/client.py``; re-runs and evals cost nothing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from backend.app.repositories.mongo.collection_names import OperationalCollection as Col


class MongoLlmCacheRepository:
    """Get and put cached responses."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.LLM_CACHE]

    async def get(self, key: str) -> dict[str, Any] | None:
        return await self._col.find_one({"_id": key})

    async def put(self, key: str, *, model: str, prompt_version: str, response: dict[str, Any], tokens: dict[str, int], now: datetime) -> None:
        doc = {"_id": key, "key": key, "model": model, "prompt_version": prompt_version, "response": response, "tokens": tokens, "created_at": now}
        await self._col.replace_one({"_id": key}, doc, upsert=True)
