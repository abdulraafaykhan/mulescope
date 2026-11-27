"""Read models of the observability page: LLM cost, tokens, latency and failures.

Figures come from ``llm_calls`` (one document per attempt, written by
``llm/call_recorder.py``) plus ``case_runs`` and ``node_executions`` for the
per-run view. Costs are estimates at the list prices in ``config/llm.yaml``.
Called by ``api/routers/observability.py``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Protocol

from backend.app.core.clock import Clock
from backend.app.core.config_files import ModelPriceConfig
from backend.app.core.errors import NotFound
from backend.app.domain.enums import ObservabilityPeriod

__all__ = ["ObservabilityService"]

# Groq's free-tier limits are per minute, so the watch looks at the last minute.
RATE_WINDOW = timedelta(minutes=1)
BUCKET_BY_PERIOD = {
    ObservabilityPeriod.DAY: "hour",
    ObservabilityPeriod.WEEK: "day",
    ObservabilityPeriod.ALL: "day",
}
NO_USAGE: Mapping[str, Any] = {
    "attempts": 0,
    "requests": 0,
    "errors": 0,
    "cache_hits": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "cost_usd": 0.0,
    "saved_cost_usd": 0.0,
    "llm_latency_ms": 0,
}


class LlmCallReadPort(Protocol):
    async def summary(
        self, since: datetime, bucket_unit: str, rate_since: datetime
    ) -> dict[str, Any]: ...
    async def for_run(self, run_id: str) -> list[dict[str, Any]]: ...
    async def totals_by_run(self, run_ids: list[str]) -> dict[str, dict[str, Any]]: ...


class RunReadPort(Protocol):
    async def get(self, run_id: str) -> dict[str, Any] | None: ...
    async def recent(self, since: datetime, limit: int) -> list[dict[str, Any]]: ...


class NodeExecReadPort(Protocol):
    async def for_run(self, run_id: str) -> list[dict[str, Any]]: ...


def _rate(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _requests_by_agent(rows: list[dict[str, Any]]) -> dict[str | None, dict[str, Any]]:
    return {r["agent"]: r for r in rows}


class ObservabilityService:
    """Summary, run list and run detail for the observability page."""

    def __init__(
        self,
        *,
        calls: LlmCallReadPort,
        runs: RunReadPort,
        node_execs: NodeExecReadPort,
        models: Mapping[str, ModelPriceConfig],
        retention: timedelta,
        clock: Clock,
    ) -> None:
        self._calls, self._runs, self._node_execs = calls, runs, node_execs
        self._models, self._retention, self._clock = models, retention, clock

    def _since(self, period: ObservabilityPeriod, now: datetime) -> datetime:
        spans = {
            ObservabilityPeriod.DAY: timedelta(days=1),
            ObservabilityPeriod.WEEK: timedelta(weeks=1),
            ObservabilityPeriod.ALL: self._retention,
        }
        return now - spans[period]

    async def summary(self, period: ObservabilityPeriod) -> dict[str, Any]:
        """Tiles, breakdowns, time series and free-tier watch for ``period``."""
        now = self._clock.now()
        since = self._since(period, now)
        raw = await self._calls.summary(since, BUCKET_BY_PERIOD[period], now - RATE_WINDOW)
        requests = _requests_by_agent(raw["requests"])
        return {
            "period": period.value,
            "since": since,
            "generated_at": now,
            "totals": self._totals(
                raw["totals"][0] if raw["totals"] else {}, list(requests.values())
            ),
            "by_agent": [
                self._agent_row(row, requests.get(row["agent"], {})) for row in raw["by_agent"]
            ],
            "by_model": raw["by_model"],
            "outcomes": raw["outcomes"],
            "series": {"bucket": BUCKET_BY_PERIOD[period], "points": raw["series"]},
            "rate_limits": self._rate_limits(raw["rate_window"]),
            "pricing": [
                {"model": name, **price.model_dump()} for name, price in self._models.items()
            ],
        }

    async def runs(self, period: ObservabilityPeriod, limit: int) -> list[dict[str, Any]]:
        """Runs started in ``period``, newest first, each with its LLM usage."""
        now = self._clock.now()
        runs = await self._runs.recent(self._since(period, now), limit)
        usage = await self._calls.totals_by_run([r["id"] for r in runs])
        return [{**r, "llm": usage.get(r["id"], NO_USAGE)} for r in runs]

    async def run_detail(self, run_id: str) -> dict[str, Any]:
        """Steps with their estimated cost, and every LLM attempt of one run.

        Raises:
            NotFound: Unknown ``run_id``.
        """
        run = await self._runs.get(run_id)
        if run is None:
            raise NotFound(f"run {run_id} not found", detail={"run_id": run_id})
        steps = await self._node_execs.for_run(run_id)
        attempts = await self._calls.for_run(run_id)
        usage = await self._calls.totals_by_run([run_id])
        cost_by_step: dict[str, float] = defaultdict(float)
        for a in attempts:
            if a.get("node_exec_id"):
                cost_by_step[a["node_exec_id"]] += a.get("cost_usd") or 0.0
        return {
            "run": {**run, "llm": usage.get(run_id, NO_USAGE)},
            "steps": [{**s, "cost_usd": cost_by_step.get(s["id"])} for s in steps],
            "attempts": attempts,
        }

    @staticmethod
    def _totals(totals: dict[str, Any], requests: list[dict[str, Any]]) -> dict[str, Any]:
        n_requests = sum(r["requests"] for r in requests)
        failed = sum(r["failed"] for r in requests)
        retried = sum(r["retried"] for r in requests)
        provider_attempts = totals.get("provider_attempts", 0)
        cache_hits = totals.get("cache_hits", 0)
        return {
            "requests": n_requests,
            "failed_requests": failed,
            "attempts": totals.get("attempts", 0),
            "provider_attempts": provider_attempts,
            "cache_hits": cache_hits,
            "errors": totals.get("provider_errors", 0),
            "tokens_in": totals.get("tokens_in", 0),
            "tokens_out": totals.get("tokens_out", 0),
            "cost_usd": totals.get("cost_usd", 0.0),
            "saved_tokens_in": totals.get("saved_tokens_in", 0),
            "saved_tokens_out": totals.get("saved_tokens_out", 0),
            "saved_cost_usd": totals.get("saved_cost_usd", 0.0),
            "avg_latency_ms": totals.get("avg_latency_ms"),
            "p95_latency_ms": totals.get("p95_latency_ms"),
            "error_rate": _rate(totals.get("provider_errors", 0), provider_attempts),
            "fallback_rate": _rate(failed, n_requests),
            "retry_rate": _rate(retried, n_requests),
            "cache_hit_rate": _rate(cache_hits, n_requests),
        }

    @staticmethod
    def _agent_row(row: dict[str, Any], requests: dict[str, Any]) -> dict[str, Any]:
        return {
            **row,
            "models": sorted(row.get("models", [])),
            "prompt_versions": sorted(row.get("prompt_versions", [])),
            "requests": requests.get("requests", 0),
            "fallbacks": requests.get("failed", 0),
        }

    def _rate_limits(self, window: list[dict[str, Any]]) -> list[dict[str, Any]]:
        used = {r["model"]: r["tokens"] for r in window}
        rows = []
        for model, price in self._models.items():
            if price.tokens_per_minute is None:
                continue
            tokens = used.get(model, 0)
            rows.append(
                {
                    "model": model,
                    "tokens_last_minute": tokens,
                    "tokens_per_minute": price.tokens_per_minute,
                    "usage_ratio": tokens / price.tokens_per_minute,
                }
            )
        return rows
