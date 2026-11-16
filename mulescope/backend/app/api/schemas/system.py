"""Response DTOs for the system routes (``/health``, ``/api/v1/config/public``).

Kept separate from the service dataclasses so the HTTP contract can evolve on
its own. Built by the routers in ``api/routers/health.py`` and ``config.py``.
"""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Body of ``GET /health``."""

    status: str
    db: str


class ProviderStatusOut(BaseModel):
    """Public status of one LLM provider. Never carries the key."""

    configured: bool
    active: bool


class PublicConfigResponse(BaseModel):
    """Body of ``GET /api/v1/config/public``."""

    llm_mode: str
    graph_version: str
    config_versions: dict[str, str]
    providers: dict[str, ProviderStatusOut]
    fallback_active: bool
