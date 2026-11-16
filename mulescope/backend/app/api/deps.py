"""FastAPI ``Depends`` providers.

Thin accessors over the container stored on ``app.state`` by the lifespan.
Nothing is constructed per request.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from backend.app.core.container import Container
from backend.app.services.system_service import SystemService


def get_container(request: Request) -> Container:
    """Return the application container."""
    container: Container = request.app.state.container
    return container


def get_system_service(request: Request) -> SystemService:
    """Return the system service."""
    service = get_container(request).system_service
    if service is None:
        raise RuntimeError("system service not initialised")
    return service


def get_extra(request: Request, name: str) -> Any:
    """Return a named application object built by ``core/wiring.py``."""
    return get_container(request).extras[name]
