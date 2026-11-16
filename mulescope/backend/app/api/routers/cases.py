"""Case routes: queue, detail, runs, decision and case data. Thin controllers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_app
from backend.app.api.schemas.requests import DecisionRequest
from backend.app.core.errors import NotFound
from backend.app.core.wiring import AppObjects

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("")
async def list_cases(status: str | None = None, priority: int | None = None, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.query.queue(status, priority)


@router.get("/{case_id}")
async def get_case(case_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.query.detail(case_id)


@router.post("/{case_id}/runs", status_code=202)
async def start_run(case_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    run = await app.runner.start_run(case_id)
    return {"run_id": run["id"], "status": run["status"]}


@router.post("/{case_id}/decision", status_code=202)
async def decide(case_id: str, body: DecisionRequest, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.runner.decide(case_id, body.model_dump())


@router.get("/{case_id}/evidence")
async def evidence(case_id: str, app: AppObjects = Depends(get_app)) -> list[dict[str, Any]]:
    return await app.query.evidence_list(case_id)


@router.get("/{case_id}/report")
async def report(case_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    rep = await app.query.report(case_id)
    if rep is None:
        raise NotFound("no report yet; start a run", detail={"case_id": case_id})
    return rep


@router.get("/{case_id}/actions")
async def actions(case_id: str, app: AppObjects = Depends(get_app)) -> list[dict[str, Any]]:
    return await app.query.actions_for(case_id)


@router.get("/{case_id}/flow")
async def flow(case_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.query.flow(case_id)


@router.get("/{case_id}/timeline")
async def timeline(case_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.query.timeline(case_id)


@router.get("/{case_id}/transactions")
async def transactions(case_id: str, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=500), app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.query.transactions(case_id, cursor, limit)


@router.get("/{case_id}/audit/verify")
async def verify_audit(case_id: str, app: AppObjects = Depends(get_app)) -> dict[str, Any]:
    return await app.audit.verify_chain(case_id)
