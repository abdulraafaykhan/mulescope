"""Response DTOs for ``/api/v1/observability`` (LLM cost, tokens, latency, failures).

Costs are USD estimates at the list prices in ``config/llm.yaml``. Latency
figures exclude cache hits (no provider time). A rate is ``None`` when its
denominator is zero. Built by ``api/routers/observability.py`` from
``services/observability_service.py``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from backend.app.domain.enums import LlmCallOutcome


class UsageOut(BaseModel):
    """Attempts, requests, tokens and cost of a set of LLM calls."""

    attempts: int
    errors: int
    tokens_in: int
    tokens_out: int
    cost_usd: float


class LatencyOut(BaseModel):
    """Provider latency of a set of attempts."""

    avg_latency_ms: float | None
    p95_latency_ms: float | None


class SummaryTotalsOut(UsageOut, LatencyOut):
    """Tiles of the observability page.

    ``requests`` are structured calls (one per agent step); ``attempts`` are
    every provider call and cache hit inside them. ``failed_requests`` ended
    on the agent's template. ``errors`` counts failed provider attempts.
    """

    requests: int
    failed_requests: int
    provider_attempts: int
    cache_hits: int
    saved_tokens_in: int
    saved_tokens_out: int
    saved_cost_usd: float
    error_rate: float | None
    fallback_rate: float | None
    retry_rate: float | None
    cache_hit_rate: float | None


class AgentUsageOut(UsageOut, LatencyOut):
    """One agent: what it ran on and what it cost."""

    agent: str | None
    models: list[str]
    prompt_versions: list[str]
    requests: int
    fallbacks: int


class ModelUsageOut(UsageOut, LatencyOut):
    """One model."""

    model: str


class OutcomeCountOut(BaseModel):
    outcome: LlmCallOutcome
    count: int


class SeriesPointOut(UsageOut):
    """One time bucket (start of the IST hour or day)."""

    ts: datetime


class SeriesOut(BaseModel):
    bucket: str
    points: list[SeriesPointOut]


class RateLimitOut(BaseModel):
    """Tokens used in the last minute against the free-tier limit of one model."""

    model: str
    tokens_last_minute: int
    tokens_per_minute: int
    usage_ratio: float


class ModelPriceOut(BaseModel):
    """List price the estimates use."""

    model: str
    input_usd_per_million: float
    output_usd_per_million: float
    tokens_per_minute: int | None


class ObservabilitySummaryResponse(BaseModel):
    """Body of ``GET /api/v1/observability/summary``."""

    period: str
    since: datetime
    generated_at: datetime
    totals: SummaryTotalsOut
    by_agent: list[AgentUsageOut]
    by_model: list[ModelUsageOut]
    outcomes: list[OutcomeCountOut]
    series: SeriesOut
    rate_limits: list[RateLimitOut]
    pricing: list[ModelPriceOut]


class RunUsageOut(UsageOut):
    """LLM usage of one run."""

    requests: int
    cache_hits: int
    saved_cost_usd: float
    llm_latency_ms: int


class RunTotalsOut(BaseModel):
    """Totals ``finalize`` stored on the run (absent until the run ends)."""

    tokens: int
    latency_ms: int
    retries: int
    fallback_nodes: int | None = None
    cost_usd: float | None = None


class RunRowOut(BaseModel):
    """One run in the runs table."""

    id: str
    case_id: str
    status: str
    llm_mode: str
    graph_version: str
    models: dict[str, str]
    prompt_versions: dict[str, str]
    started_at: datetime
    ended_at: datetime | None
    final_disposition: str | None = None
    totals: RunTotalsOut
    llm: RunUsageOut


class StepOut(BaseModel):
    """One node execution with its estimated LLM cost (``None`` when it made no call)."""

    id: str
    node: str
    agent: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    latency_ms: int | None
    model: str | None = None
    prompt_version: str | None = None
    tokens_in: int
    tokens_out: int
    retries: int
    cache_hit: bool = False
    fallback_used: bool
    fallback_reason: str | None = None
    error: str | None = None
    output_summary: str | None = None
    cost_usd: float | None


class AttemptOut(BaseModel):
    """One LLM call attempt."""

    id: str
    call_id: str
    node: str | None
    agent: str | None
    node_exec_id: str | None
    provider: str
    model: str
    prompt_version: str
    attempt: int
    outcome: LlmCallOutcome
    latency_ms: int
    tokens_in: int
    tokens_out: int
    saved_tokens_in: int
    saved_tokens_out: int
    cost_usd: float | None
    saved_cost_usd: float | None
    error: str | None
    created_at: datetime


class RunDetailResponse(BaseModel):
    """Body of ``GET /api/v1/observability/runs/{run_id}``."""

    run: RunRowOut
    steps: list[StepOut]
    attempts: list[AttemptOut]
