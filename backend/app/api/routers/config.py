"""``GET /api/v1/config/public``: LLM mode, versions and provider status."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_system_service
from backend.app.api.schemas.system import ProviderStatusOut, PublicConfigResponse
from backend.app.services.system_service import SystemService

router = APIRouter(tags=["system"])


@router.get("/config/public", response_model=PublicConfigResponse)
async def public_config(
    service: SystemService = Depends(get_system_service),
) -> PublicConfigResponse:
    """Return configuration that is safe for any client. Never includes keys."""
    cfg = service.public_config()
    return PublicConfigResponse(
        llm_mode=cfg.llm_mode.value,
        graph_version=cfg.graph_version,
        config_versions=dict(cfg.config_versions),
        providers={
            "groq": ProviderStatusOut(
                configured=cfg.providers.groq.configured, active=cfg.providers.groq.active
            ),
            "gemini": ProviderStatusOut(
                configured=cfg.providers.gemini.configured, active=cfg.providers.gemini.active
            ),
        },
        fallback_active=cfg.fallback_active,
    )
