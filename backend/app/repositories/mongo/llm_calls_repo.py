"""``llm_calls``: one document per LLM call attempt (the observability log).

Written by ``llm/call_recorder.py``; read by ``services/observability_service.py``
and by the graph's ``finalize`` node for the run's estimated cost. Reads use the
``run_id`` index or the ``created_at`` TTL index, and aggregate in MongoDB.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from backend.app.domain.enums import LlmCallOutcome
from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.convert import plain

__all__ = ["MongoLlmCallRepository"]

P95 = 0.95
# Buckets of the time series follow the IST calendar the UI shows.
DISPLAY_TIMEZONE = "Asia/Kolkata"

_SUCCESS = [LlmCallOutcome.OK.value, LlmCallOutcome.CACHE_HIT.value]
_IS_PROVIDER_CALL = {"$ne": ["$outcome", LlmCallOutcome.CACHE_HIT.value]}
_IS_SUCCESS = {"$in": ["$outcome", _SUCCESS]}
# Cache hits take no provider time, so they are left out of latency figures.
_PROVIDER_LATENCY = {"$cond": [_IS_PROVIDER_CALL, "$latency_ms", None]}


def _count_if(condition: dict[str, Any]) -> dict[str, Any]:
    return {"$sum": {"$cond": [condition, 1, 0]}}


def _usage() -> dict[str, Any]:
    return {
        "attempts": {"$sum": 1},
        "errors": {"$sum": {"$cond": [_IS_SUCCESS, 0, 1]}},
        "tokens_in": {"$sum": "$tokens_in"},
        "tokens_out": {"$sum": "$tokens_out"},
        "cost_usd": {"$sum": "$cost_usd"},
    }


def _latency() -> dict[str, Any]:
    return {
        "avg_latency_ms": {"$avg": _PROVIDER_LATENCY},
        "p95_latency_ms": {
            "$percentile": {"input": _PROVIDER_LATENCY, "p": [P95], "method": "approximate"}
        },
    }


def _keyed(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Rename the ``$group`` key to ``key`` and unwrap the one-value percentile."""
    out = []
    for row in rows:
        row = dict(row)
        row[key] = row.pop("_id")
        if isinstance(row.get("p95_latency_ms"), list):
            row["p95_latency_ms"] = row["p95_latency_ms"][0]
        out.append(row)
    return out


class MongoLlmCallRepository:
    """Insert and aggregate LLM call attempts."""

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        self._col = db[Col.LLM_CALLS]

    async def insert(self, doc: dict[str, Any]) -> None:
        await self._col.insert_one(doc)

    async def for_run(self, run_id: str) -> list[dict[str, Any]]:
        """Every attempt of one run, oldest first."""
        cursor = self._col.find({"run_id": run_id}).sort([("created_at", 1), ("_id", 1)])
        return [plain(d) async for d in cursor]  # type: ignore[misc]

    async def totals_by_run(self, run_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Usage per run for ``run_ids``; runs without attempts are absent."""
        if not run_ids:
            return {}
        pipeline = [
            {"$match": {"run_id": {"$in": run_ids}}},
            {
                "$group": {
                    "_id": "$run_id",
                    **_usage(),
                    "call_ids": {"$addToSet": "$call_id"},
                    "cache_hits": _count_if({"$not": [_IS_PROVIDER_CALL]}),
                    "saved_cost_usd": {"$sum": "$saved_cost_usd"},
                    "llm_latency_ms": {"$sum": _PROVIDER_LATENCY},
                }
            },
            {"$addFields": {"requests": {"$size": "$call_ids"}}},
            {"$project": {"call_ids": 0}},
        ]
        rows = await (await self._col.aggregate(pipeline)).to_list()
        return {r.pop("_id"): r for r in rows}

    async def summary(
        self, since: datetime, bucket_unit: str, rate_since: datetime
    ) -> dict[str, Any]:
        """Every figure of the observability page for attempts since ``since``.

        One ``$facet`` query over the ``created_at`` index.

        Args:
            since: Start of the period.
            bucket_unit: ``$dateTrunc`` unit of the time series (``hour``, ``day``).
            rate_since: Start of the rate-limit window (tokens per model).

        Returns:
            ``totals`` (one row or none), ``requests`` (per agent: requests,
            failed, retried), ``by_agent``, ``by_model``, ``outcomes``,
            ``series`` and ``rate_window`` (tokens per model since ``rate_since``).
        """
        facets: dict[str, list[dict[str, Any]]] = {
            "totals": [
                {
                    "$group": {
                        "_id": None,
                        **_usage(),
                        **_latency(),
                        "provider_attempts": _count_if(_IS_PROVIDER_CALL),
                        "provider_errors": _count_if(
                            {
                                "$and": [
                                    _IS_PROVIDER_CALL,
                                    {"$ne": ["$outcome", LlmCallOutcome.OK.value]},
                                ]
                            }
                        ),
                        "cache_hits": _count_if({"$not": [_IS_PROVIDER_CALL]}),
                        "saved_tokens_in": {"$sum": "$saved_tokens_in"},
                        "saved_tokens_out": {"$sum": "$saved_tokens_out"},
                        "saved_cost_usd": {"$sum": "$saved_cost_usd"},
                    }
                }
            ],
            # A request is one structured call; it failed (the agent used its
            # template) when none of its attempts succeeded.
            "requests": [
                {
                    "$group": {
                        "_id": "$call_id",
                        "agent": {"$first": "$agent"},
                        "attempts": {"$sum": 1},
                        "succeeded": {"$max": {"$cond": [_IS_SUCCESS, 1, 0]}},
                    }
                },
                {
                    "$group": {
                        "_id": "$agent",
                        "requests": {"$sum": 1},
                        "failed": {"$sum": {"$subtract": [1, "$succeeded"]}},
                        "retried": _count_if({"$gt": ["$attempts", 1]}),
                    }
                },
            ],
            "by_agent": [
                {
                    "$group": {
                        "_id": "$agent",
                        **_usage(),
                        **_latency(),
                        "models": {"$addToSet": "$model"},
                        "prompt_versions": {"$addToSet": "$prompt_version"},
                    }
                },
                {"$sort": {"_id": 1}},
            ],
            "by_model": [
                {"$group": {"_id": "$model", **_usage(), **_latency()}},
                {"$sort": {"_id": 1}},
            ],
            "outcomes": [
                {"$group": {"_id": "$outcome", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ],
            "series": [
                {
                    "$group": {
                        "_id": {
                            "$dateTrunc": {
                                "date": "$created_at",
                                "unit": bucket_unit,
                                "timezone": DISPLAY_TIMEZONE,
                            }
                        },
                        **_usage(),
                    }
                },
                {"$sort": {"_id": 1}},
            ],
            "rate_window": [
                {
                    "$match": {
                        "created_at": {"$gte": rate_since},
                        "outcome": {"$ne": LlmCallOutcome.CACHE_HIT.value},
                    }
                },
                {
                    "$group": {
                        "_id": "$model",
                        "tokens": {"$sum": {"$add": ["$tokens_in", "$tokens_out"]}},
                    }
                },
            ],
        }
        pipeline = [{"$match": {"created_at": {"$gte": since}}}, {"$facet": facets}]
        raw = (await (await self._col.aggregate(pipeline)).to_list())[0]
        return {
            "totals": _keyed(raw["totals"], "key"),
            "requests": _keyed(raw["requests"], "agent"),
            "by_agent": _keyed(raw["by_agent"], "agent"),
            "by_model": _keyed(raw["by_model"], "model"),
            "outcomes": _keyed(raw["outcomes"], "outcome"),
            "series": [plain(r) for r in _keyed(raw["series"], "ts")],
            "rate_window": _keyed(raw["rate_window"], "model"),
        }
