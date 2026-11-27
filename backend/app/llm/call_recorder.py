"""Stores each LLM call attempt in ``llm_calls`` with its node and estimated cost.

``LlmCallRecorder`` is the :class:`AttemptSink` the live ``LlmClient`` uses.
It labels the attempt with the current :class:`NodeScope`, estimates its cost
from the list prices in ``config/llm.yaml`` and writes one document. Built by
``llm/factory.py``; read back by ``services/observability_service.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from backend.app.core.clock import Clock
from backend.app.core.config_files import ModelPriceConfig
from backend.app.core.logging import get_logger
from backend.app.core.node_scope import current_node_scope
from backend.app.llm.telemetry import LlmAttempt

__all__ = ["LlmCallRecorder", "LlmCallWritePort", "estimate_cost_usd"]

_logger = get_logger(__name__)
TOKENS_PER_MILLION = 1_000_000


class LlmCallWritePort(Protocol):
    async def insert(self, doc: dict[str, Any]) -> None: ...


def estimate_cost_usd(
    price: ModelPriceConfig | None, tokens_in: int, tokens_out: int
) -> float | None:
    """Estimated USD cost of ``tokens_in`` prompt and ``tokens_out`` completion tokens.

    Args:
        price: List price of the model, or ``None`` when the model is not priced.
        tokens_in: Prompt tokens.
        tokens_out: Completion tokens.

    Returns:
        The estimate, or ``None`` for an unpriced model.
    """
    if price is None:
        return None
    usd = tokens_in * price.input_usd_per_million + tokens_out * price.output_usd_per_million
    return usd / TOKENS_PER_MILLION


class LlmCallRecorder:
    """Writes one ``llm_calls`` document per attempt."""

    def __init__(
        self, calls: LlmCallWritePort, prices: Mapping[str, ModelPriceConfig], clock: Clock
    ) -> None:
        self._calls, self._prices, self._clock = calls, prices, clock

    async def record(self, attempt: LlmAttempt) -> None:
        """Label, price and store ``attempt``. Never raises.

        Args:
            attempt: The attempt reported by ``LlmClient``.
        """
        scope = current_node_scope()
        price = self._prices.get(attempt.model)
        doc = {
            "call_id": attempt.call_id,
            "case_id": scope.case_id if scope else None,
            "run_id": scope.run_id if scope else None,
            "node": scope.node if scope else None,
            "agent": scope.agent if scope else None,
            "node_exec_id": scope.node_exec_id if scope else None,
            "provider": attempt.provider,
            "model": attempt.model,
            "prompt_version": attempt.prompt_version,
            "attempt": attempt.attempt,
            "outcome": attempt.outcome.value,
            "latency_ms": attempt.latency_ms,
            "tokens_in": attempt.tokens_in,
            "tokens_out": attempt.tokens_out,
            "saved_tokens_in": attempt.saved_tokens_in,
            "saved_tokens_out": attempt.saved_tokens_out,
            "cost_usd": estimate_cost_usd(price, attempt.tokens_in, attempt.tokens_out),
            "saved_cost_usd": estimate_cost_usd(
                price, attempt.saved_tokens_in, attempt.saved_tokens_out
            ),
            "error": attempt.error,
            "created_at": self._clock.now(),
        }
        try:
            await self._calls.insert(doc)
        except Exception:
            # Why: the call log is diagnostics; losing a row must never fail or
            # stall a case. The node's own meta and the log line still exist.
            _logger.warning(
                "llm call attempt not recorded", exc_info=True, extra={"outcome": doc["outcome"]}
            )
