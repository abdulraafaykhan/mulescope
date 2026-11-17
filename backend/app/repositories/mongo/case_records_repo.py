"""Write-side repositories for investigation records.

One small class per collection: ``counters`` (readable id sequences),
``evidence``, ``reports``, ``actions``, ``decisions``, ``case_runs`` and
``node_executions``. Only the methods the graph and routes need.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.convert import plain


class MongoCounterRepository:
    """Atomic sequences for readable ids (EVD-, RUN-, ACT-, RPT-, DEC-)."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.COUNTERS]

    async def next_ids(self, name: str, prefix: str, n: int, now: datetime, width: int = 6) -> list[str]:
        doc = await self._col.find_one_and_update(
            {"_id": name}, {"$inc": {"value": n}, "$setOnInsert": {"created_at": now}}, upsert=True, return_document=ReturnDocument.AFTER
        )
        end = int(doc["value"])
        return [f"{prefix}{i:0{width}d}" for i in range(end - n + 1, end + 1)]


class MongoEvidenceRepository:
    """The evidence ledger."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.EVIDENCE]

    async def insert_many(self, docs: list[dict[str, Any]]) -> None:
        if docs:
            await self._col.insert_many(docs, ordered=False)

    async def for_run(self, case_id: str, run_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find({"case_id": case_id, "run_id": run_id}).sort("_id", 1)
        return [plain(d) async for d in cursor]  # type: ignore[misc]


class MongoReportRepository:
    """Versioned narrative and STR drafts."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.REPORTS]

    async def insert(self, doc: dict[str, Any]) -> None:
        await self._col.insert_one(doc)

    async def latest(self, case_id: str) -> dict[str, Any] | None:
        return plain(await self._col.find_one({"case_id": case_id}, sort=[("version", -1)]))

    async def update(self, report_id: str, fields: dict[str, Any]) -> None:
        await self._col.update_one({"_id": report_id}, {"$set": fields})

    async def next_version(self, case_id: str) -> int:
        latest = await self._col.find_one({"case_id": case_id}, {"version": 1}, sort=[("version", -1)])
        return int(latest["version"]) + 1 if latest else 1


class MongoActionRepository:
    """Proposed and executed actions; idempotent on ``idempotency_key``."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.ACTIONS]

    async def upsert_proposed(self, doc: dict[str, Any]) -> bool:
        """Insert unless an action with the same idempotency key exists."""
        existing = await self._col.find_one({"idempotency_key": doc["idempotency_key"]}, {"_id": 1})
        if existing:
            return False
        await self._col.insert_one(doc)
        return True

    async def for_case(self, case_id: str) -> list[dict[str, Any]]:
        return [plain(d) async for d in self._col.find({"case_id": case_id}).sort("_id", 1)]  # type: ignore[misc]

    async def get(self, action_id: str) -> dict[str, Any] | None:
        return plain(await self._col.find_one({"_id": action_id}))

    async def update(self, action_id: str, fields: dict[str, Any], history: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        doc = await self._col.find_one_and_update(
            {"_id": action_id}, {"$set": {**fields, "updated_at": now}, "$push": {"history": history}}, return_document=ReturnDocument.AFTER
        )
        return plain(doc)


class MongoDecisionRepository:
    """Analyst decisions."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.DECISIONS]

    async def insert(self, doc: dict[str, Any]) -> None:
        await self._col.insert_one(doc)

    async def for_case(self, case_id: str) -> list[dict[str, Any]]:
        return [plain(d) async for d in self._col.find({"case_id": case_id}).sort("created_at", 1)]  # type: ignore[misc]


class MongoRunRepository:
    """``case_runs``: one document per graph execution."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.CASE_RUNS]

    async def insert(self, doc: dict[str, Any]) -> None:
        await self._col.insert_one(doc)

    async def get(self, run_id: str) -> dict[str, Any] | None:
        return plain(await self._col.find_one({"_id": run_id}))

    async def update(self, run_id: str, fields: dict[str, Any], now: datetime) -> None:
        await self._col.update_one({"_id": run_id}, {"$set": {**fields, "updated_at": now}})

    async def latest_for_case(self, case_id: str) -> dict[str, Any] | None:
        return plain(await self._col.find_one({"case_id": case_id}, sort=[("started_at", -1)]))

    async def latest_for_cases(self, case_ids: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        async for d in self._col.find({"case_id": {"$in": case_ids}}).sort("started_at", 1):
            out[d["case_id"]] = plain(d)  # type: ignore[assignment]
        return out


class MongoNodeExecutionRepository:
    """``node_executions``: per-node diagnostics."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.NODE_EXECUTIONS]

    async def insert(self, doc: dict[str, Any]) -> Any:
        res = await self._col.insert_one(doc)
        return res.inserted_id

    async def update(self, oid: Any, fields: dict[str, Any]) -> None:
        await self._col.update_one({"_id": oid}, {"$set": fields})

    async def for_run(self, run_id: str) -> list[dict[str, Any]]:
        return [plain(d) async for d in self._col.find({"run_id": run_id}).sort("started_at", 1)]  # type: ignore[misc]


class MongoEvalRepository:
    """Eval summaries and per-case results (no answers inside)."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._runs = db[Col.EVAL_RUNS]
        self._results = db[Col.EVAL_RESULTS]

    async def list_runs(self) -> list[dict[str, Any]]:
        return [plain(d) async for d in self._runs.find().sort("created_at", -1).limit(50)]  # type: ignore[misc]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return plain(await self._runs.find_one({"_id": run_id}))

    async def results(self, run_id: str) -> list[dict[str, Any]]:
        return [plain(d) async for d in self._results.find({"run_id": run_id})]  # type: ignore[misc]

    # --- writes: used only by the eval harness (uv run evals) ---------------

    async def create_run(self, doc: dict[str, Any]) -> None:
        await self._runs.insert_one(doc)

    async def update_run(self, run_id: str, fields: dict[str, Any]) -> None:
        await self._runs.update_one({"_id": run_id}, {"$set": fields})

    async def latest_unfinished(self, mode: str) -> dict[str, Any] | None:
        """Most recent eval run in ``mode`` that has not completed (resume target)."""
        return plain(await self._runs.find_one({"mode": mode, "status": "running"}, sort=[("created_at", -1)]))

    async def save_result(self, doc: dict[str, Any]) -> None:
        """Upsert one per-case result; ``_id`` is ``run_id:case_id`` so reruns replace it."""
        await self._results.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def done_case_ids(self, run_id: str) -> set[str]:
        """Cases already evaluated without error in ``run_id`` (skipped on resume)."""
        return {d["case_id"] async for d in self._results.find({"run_id": run_id, "error": None}, {"case_id": 1})}
