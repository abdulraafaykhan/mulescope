"""FastAPI app factory and the ``uv run dev`` entry point.

``create_app`` builds the app; its lifespan creates the container (clients,
bootstrap, checkpointer, graph, services) once and closes it on shutdown.
``/health`` is mounted at the root; every other route lives under ``/api/v1``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.error_handlers import register_error_handlers
from backend.app.api.routers import API_ROUTERS
from backend.app.api.routers.health import router as health_router
from backend.app.core.container import Container
from backend.app.core.logging import configure_logging
from backend.app.core.settings import ApiSettings

API_PREFIX = "/api/v1"


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: Optional settings override (tests, scripts). Defaults to env.

    Returns:
        The configured app. The container is created in the lifespan.
    """
    configure_logging()
    app_settings = settings or ApiSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = Container(app_settings)
        await container.startup()
        app.state.container = container
        try:
            yield
        finally:
            await container.shutdown()

    app = FastAPI(title="MuleScope API", version=app_settings.graph_version, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health_router)
    for router in API_ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
    return app


def run() -> None:
    """Entry point for ``uv run dev``: serve the app with uvicorn."""
    settings = ApiSettings()
    uvicorn.run(
        "backend.app.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
    )
