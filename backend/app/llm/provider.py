"""The ``LLMProvider`` interface and its request/response value objects.

Every provider (Groq, Gemini) is substitutable behind ``LLMProvider``: it
takes an ``LlmRequest`` and returns raw JSON text plus token counts. Retries,
caching, the semaphore and schema validation live in ``llm/client.py``, so
providers stay thin. The deterministic fallback is not a provider: each agent
falls back to its template implementation (``agents/*.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LlmRequest:
    """One structured-output call.

    Attributes:
        system: System prompt (versioned file content).
        user: User message; untrusted text is already wrapped in ``<untrusted_data>``.
        model: Provider model id from ``config/llm.yaml``.
        temperature: Sampling temperature (0 for reproducibility).
        max_tokens: Output token budget.
        reasoning_effort: ``low``, ``medium`` or ``high`` for providers that
            support it (Groq gpt-oss); ``None`` keeps the provider default.
    """

    system: str
    user: str
    model: str
    temperature: float
    max_tokens: int
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class LlmResponse:
    """Raw provider output.

    Attributes:
        text: The model's JSON text (not yet validated).
        tokens_in: Prompt tokens reported by the provider.
        tokens_out: Completion tokens reported by the provider.
        model: Model id that served the request.
    """

    text: str
    tokens_in: int
    tokens_out: int
    model: str


class ProviderError(Exception):
    """A provider call failed.

    Args:
        message: What went wrong (never includes the API key).
        retryable: True for rate limits, timeouts and 5xx responses.
        retry_after: Seconds the provider asked us to wait, if it said.
        status: HTTP status of the response, ``None`` for transport errors.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        retry_after: float | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after
        self.status = status


class LLMProvider(Protocol):
    """A chat model that returns JSON text for a request."""

    name: str

    async def complete(self, request: LlmRequest) -> LlmResponse:
        """Run one request.

        Raises:
            ProviderError: On any HTTP, quota or response-shape failure.
        """
        ...

    async def aclose(self) -> None:
        """Release the HTTP client."""
        ...
