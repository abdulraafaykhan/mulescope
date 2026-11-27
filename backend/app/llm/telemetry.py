"""What ``LlmClient`` reports about each call attempt, and where it reports it.

``LlmClient`` builds one :class:`LlmAttempt` per provider call (and one per
cache hit) and hands it to an :class:`AttemptSink`. The client knows nothing
about storage, node identity or prices; ``llm/call_recorder.py`` adds those.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.app.domain.enums import LlmCallOutcome

__all__ = ["AttemptSink", "LlmAttempt"]


@dataclass(frozen=True, slots=True)
class LlmAttempt:
    """One provider call, or one cache hit, inside a structured call.

    Attributes:
        call_id: Shared by every attempt of the same structured call.
        provider: Provider name (``groq``, ``gemini``).
        model: Model that was asked (or that produced the cached answer).
        prompt_version: Prompt file stem, for example ``profiler.v1``.
        attempt: 1-based position of this attempt within the structured call.
        outcome: How the attempt ended.
        latency_ms: Provider time, excluding the wait for a concurrency slot.
        tokens_in: Prompt tokens the provider reported.
        tokens_out: Completion tokens the provider reported.
        saved_tokens_in: For a cache hit, prompt tokens the original call used.
        saved_tokens_out: For a cache hit, completion tokens the original call used.
        error: Short error text for a failed attempt (never a prompt or key).
    """

    call_id: str
    provider: str
    model: str
    prompt_version: str
    attempt: int
    outcome: LlmCallOutcome
    latency_ms: int
    tokens_in: int = 0
    tokens_out: int = 0
    saved_tokens_in: int = 0
    saved_tokens_out: int = 0
    error: str | None = None


class AttemptSink(Protocol):
    """Receives every attempt. Implementations must not raise."""

    async def record(self, attempt: LlmAttempt) -> None:
        """Store or forward one attempt."""
        ...
