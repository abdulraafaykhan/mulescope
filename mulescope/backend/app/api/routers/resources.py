"""Alerts, accounts, actions, audit, runs (SSE stream, diagnostics) and evals."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.app.api.deps import get_app, get_container
from backend.app.api.schemas.requests import ActionPatch
from backend.app.core.container import Container
from backend.app.core.errors import NotFound, PolicyViolation
from backend.app.core.wiring import AppObjects
from backend.app.services.detection import dataset_window_end

alerts = APIRouter(prefix="/alerts", tags=["alerts"])
accounts = APIRouter(prefix="/accounts", tags=["accounts"])
actions = APIRouter(prefix="/actions", tags=["actions"])
audit = APIRouter(prefix="/audit", tags=["audit"])
runs = APIRouter(prefix="/runs", tags=["runs"])
evals = APIRouter(prefix="/evals", tags=["evals"])


@alerts.get("")
async def list_alerts(status: str | None = None, app: AppObjects = Depends(get_app)) -> list[dict[str, Any]]:
    return await app.alerts.list(status=status)


@alerts.get("/{alert_id}")
async def get_alert(alert_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    alert = await app.alerts.get(alert_id)
    if alert is None:
        raise NotFound(f"alert {alert_id} not found")
    return alert


@alerts.post("/detect")
async def detect(container: Container = Depends(get_container), app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    result = await app.detector.detect(dataset_window_end(container.settings.as_of_date))
    return {"window_start": result.window_start, "window_end": result.window_end, "scanned_accounts": result.scanned_accounts, "alerts_created": len(result.alerts_created), "skipped_existing": result.skipped_existing}


@accounts.get("/{account_id}")
async def get_account(account_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    acct = await app.deps.accounts.get(account_id)
    if acct is None:
        raise NotFound(f"account {account_id} not found")
    return acct


@accounts.get("/{account_id}/summary")
async def account_summary(account_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.query.account_summary(account_id)


@actions.patch("/{action_id}")
async def patch_action(action_id: str, body: ActionPatch, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.actions.change(action_id, body.op, body.user_id, body.reason)


@audit.get("")
async def list_audit(case_id: str | None = None, event: str | None = None, limit: int = 200, app: AppObjects = Depends(get_app)) -> list[dict[str, Any]]:
    return await app.audit.list(case_id=case_id, event=event, limit=min(limit, 1000))


@runs.get("/{run_id}/stream")
async def stream(run_id: str, app: AppObjects = Depends(get_app)) -> StreamingResponse:
    """Server-Sent Events for one run: history replay, then live events."""

    async def events() -> AsyncIterator[str]:
        async for event in app.bus.subscribe(run_id):
            yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@runs.get("/{run_id}/diagnostics")
async def diagnostics(run_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.query.diagnostics(run_id)


@evals.get("/runs")
async def eval_runs(app: AppObjects = Depends(get_app)) -> list[dict[str, Any]]:
    return await app.evals.list_runs()


@evals.get("/runs/{run_id}")
async def eval_run(run_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    run = await app.evals.get_run(run_id)
    if run is None:
        raise NotFound(f"eval run {run_id} not found")
    return {"run": run, "results": await app.evals.results(run_id)}


@evals.post("/runs")
async def start_eval() -> dict[str, Any]:
    # The API never opens the truth database, so evals run from the CLI.
    raise PolicyViolation("evals run from the CLI: uv run evals --mode fallback")
