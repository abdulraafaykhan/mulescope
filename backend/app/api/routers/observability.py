"""Observability: estimated LLM cost, tokens, latency and failures (thin controller)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_app
from backend.app.api.schemas.observability import (
    ObservabilitySummaryResponse,
    RunDetailResponse,
    RunRowOut,
)
from backend.app.core.wiring import AppObjects
from backend.app.domain.enums import ObservabilityPeriod

router = APIRouter(prefix="/observability", tags=["observability"])

App = Annotated[AppObjects, Depends(get_app)]
RUNS_DEFAULT_LIMIT = 50
RUNS_MAX_LIMIT = 200


@router.get("/summary", response_model=ObservabilitySummaryResponse)
async def summary(
    app: App, period: ObservabilityPeriod = ObservabilityPeriod.WEEK
) -> dict[str, Any]:
    """Tiles, breakdowns, time series and free-tier watch for one period."""
    return await app.observability.summary(period)


@router.get("/runs", response_model=list[RunRowOut])
async def runs(
    app: App,
    period: ObservabilityPeriod = ObservabilityPeriod.WEEK,
    limit: Annotated[int, Query(ge=1, le=RUNS_MAX_LIMIT)] = RUNS_DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Runs started in the period, newest first, with their LLM usage."""
    return await app.observability.runs(period, limit)


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def run_detail(run_id: str, app: App) -> dict[str, Any]:
    """Steps and every LLM attempt of one run. 404 for an unknown run."""
    return await app.observability.run_detail(run_id)
