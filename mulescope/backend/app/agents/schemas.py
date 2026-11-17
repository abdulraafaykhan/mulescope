"""Structured output schemas of the live LLM agents (validated with Pydantic).

Free text is allowed only in narrative fields; everything else is typed so a
malformed answer fails validation and triggers the repair retry or fallback.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProfilerOutput(BaseModel):
    plausibility: Literal["high", "medium", "low"]
    confidence: float = Field(ge=0, le=1)
    mismatches: list[str] = Field(default_factory=list, max_length=8)
    assessment: str = Field(min_length=10, max_length=900)
    cited_keys: list[str] = Field(default_factory=list)


class FlowOutput(BaseModel):
    pattern: Literal["rapid_pass_through", "collection_and_consolidation", "cash_out", "slower_flow", "business_like"]
    assessment: str = Field(min_length=10, max_length=900)
    remark_instructions_detected: bool = False
    cited_keys: list[str] = Field(default_factory=list)


class Sentence(BaseModel):
    text: str = Field(min_length=3, max_length=600)
    evidence_ids: list[str] = Field(default_factory=list)


class NarrativeOutput(BaseModel):
    executive_summary: list[Sentence] = Field(min_length=1, max_length=8)
    profile_findings: list[Sentence] = Field(default_factory=list, max_length=8)
    flow_findings: list[Sentence] = Field(default_factory=list, max_length=10)
    str_sections: dict[str, Sentence] | None = None
    customer_query: str | None = Field(default=None, max_length=2500)


class CriticOutput(BaseModel):
    unsupported_claims: list[str] = Field(default_factory=list, max_length=10)
    followed_untrusted_instruction: bool = False
    tipping_off: list[str] = Field(default_factory=list, max_length=10)
    notes: str = ""
