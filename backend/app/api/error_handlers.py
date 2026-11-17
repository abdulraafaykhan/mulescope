"""Single mapping from domain errors to HTTP responses.

Registered once by ``main.create_app``. Walks the exception MRO so subclasses
map to the closest entry. Unhandled exceptions become a 500 envelope without
leaking internals.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.api.schemas.errors import ErrorBody, ErrorEnvelope
from backend.app.core.errors import (
    DependencyUnavailable,
    DomainError,
    LLMUnavailable,
    NotFound,
    PolicyViolation,
)
from backend.app.core.logging import get_logger

_logger = get_logger(__name__)

# Ordered from most to least specific; the MRO walk picks the first hit.
_STATUS: dict[type[DomainError], tuple[int, str]] = {
    NotFound: (404, "not_found"),
    PolicyViolation: (409, "policy_violation"),
    LLMUnavailable: (503, "llm_unavailable"),
    DependencyUnavailable: (503, "dependency_unavailable"),
    DomainError: (400, "domain_error"),
}


def _resolve(exc: DomainError) -> tuple[int, str]:
    """Return ``(status, code)`` for the nearest mapped class in the MRO."""
    for cls in type(exc).__mro__:
        if cls in _STATUS:
            return _STATUS[cls]  # type: ignore[index]
    return _STATUS[DomainError]


def _envelope(status: int, code: str, message: str, detail: object | None) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message, detail=detail))
    return JSONResponse(status_code=status, content=body.model_dump())


def register_error_handlers(app: FastAPI) -> None:
    """Attach the domain and fallback exception handlers to ``app``.

    Args:
        app: The FastAPI application.
    """

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        status, code = _resolve(exc)
        _logger.warning("domain error", extra={"code": code, "status": status})
        return _envelope(status, code, exc.message, exc.detail)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        _logger.exception("unhandled error", extra={"error_type": type(exc).__name__})
        return _envelope(500, "internal_error", "Internal server error", None)
