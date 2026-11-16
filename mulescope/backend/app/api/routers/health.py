"""``GET /health`` at the root path (operational probe, not versioned)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_system_service
from backend.app.api.schemas.system import HealthResponse
from backend.app.services.system_service import SystemService

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(service: SystemService = Depends(get_system_service)) -> HealthResponse:
    """Ping MongoDB. A failed ping raises ``DependencyUnavailable`` -> 503."""
    result = await service.check_health()
    return HealthResponse(status=result.status.value, db=result.db.value)
