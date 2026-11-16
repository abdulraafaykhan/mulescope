"""Error envelope returned by every failed request.

Shape: ``{"error": {"code": str, "message": str, "detail": object | null}}``.
Produced only by ``api/error_handlers.py``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    """Inner error object."""

    code: str
    message: str
    detail: Any | None = None


class ErrorEnvelope(BaseModel):
    """Outer error envelope."""

    error: ErrorBody
