"""Request bodies for the write endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DecisionRequest(BaseModel):
    """Analyst decision that resumes the paused graph."""

    decision: Literal["approve", "edit", "override", "request_more", "reject"]
    user_id: str = "analyst-1"
    role: Literal["analyst", "senior_reviewer"] = "analyst"
    reason: str | None = None
    override_disposition: Literal["close", "escalate", "str_draft"] | None = None
    edits: dict[str, Any] | None = Field(default=None, description="Edited report fields, e.g. summary_md")


class ActionPatch(BaseModel):
    """Per-action operation."""

    op: Literal["approve", "reject", "reverse"]
    user_id: str = "analyst-1"
    reason: str | None = None
