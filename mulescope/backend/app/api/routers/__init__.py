"""HTTP controllers. Thin: validate, call one service, return a schema.

``API_ROUTERS`` lists every router mounted under ``/api/v1`` by ``main.py``.
The root ``/health`` router is mounted separately.
"""

from fastapi import APIRouter

from backend.app.api.routers.config import router as config_router

API_ROUTERS: list[APIRouter] = [config_router]
