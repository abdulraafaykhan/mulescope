"""HTTP controllers. Thin: validate, call one service, return the result.

``API_ROUTERS`` lists every router mounted under ``/api/v1`` by ``main.py``.
The root ``/health`` router is mounted separately.
"""

from fastapi import APIRouter

from backend.app.api.routers.cases import router as cases_router
from backend.app.api.routers.config import router as config_router
from backend.app.api.routers.observability import router as observability_router
from backend.app.api.routers.resources import accounts, actions, alerts, audit, evals, runs

API_ROUTERS: list[APIRouter] = [
    config_router, alerts, cases_router, accounts, actions, audit, runs, evals, observability_router,
]
