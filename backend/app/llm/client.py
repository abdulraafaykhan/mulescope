"""Structured LLM calls: cache, global semaphore, retry with backoff, schema repair.

``LlmClient.structured`` is the only way agents reach a model:

1. Look up ``llm_cache`` by ``sha256(model, prompt_version, system, user)``.
2. Otherwise try the primary model, then `fallback_model`. Each call takes the
   global semaphore (``limits.max_concurrency``) and then runs under a
   wall-clock limit (``call_timeout_seconds``), with at most ``max_attempts``
   tries and capped backoff. A timeout, or a ``Retry-After`` longer than the
   backoff cap or the remaining budget, moves on to the next model. The whole
   structured call is limited by ``node_budget_seconds``.
3. Parse the JSON and validate it into the agent's Pydantic schema; on a
   mismatch, ask once more with the validation error (repair), then give up.
4. Cache the validated output and report tokens, retries and cache hits.

On final failure it raises ``LLMUnavailable``; the agent then uses its
template implementation, so a run never fails because of an LLM.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from backend.app.core.clock import Clock
from backend.app.core.config_files import AgentModelConfig, LimitsConfig
from backend.app.core.errors import LLMUnavailable
from backend.app.core.logging import get_logger
from backend.app.llm.provider import LLMProvider, LlmRequest, ProviderError

SchemaT = TypeVar("SchemaT", bound=BaseModel)
_logger = get_logger(__name__)
_JSON_FENCE = ("```json", "```")
# Long enough to keep a Groq error code and a failed_generation excerpt.
ERROR_MAX = 700


class CachePort(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def put(self, key: str, *, model: str, prompt_version: str, response: dict[str, Any], tokens: dict[str, int], now: Any) -> None: ...


@dataclass
class CallMeta:
    """What one structured call cost; merged into the node's ``_node_meta``."""

    model: str
    prompt_version: str
    tokens_in: int = 0
    tokens_out: int = 0
    retries: int = 0
    cache_hit: bool = False
    errors: list[str] = field(default_factory=list)

    def as_meta(self) -> dict[str, Any]:
        return {"model": self.model, "prompt_version": self.prompt_version, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "retries": self.retries, "cache_hit": self.cache_hit}


def cache_key(model: str, prompt_version: str, system: str, user: str) -> str:
    """Stable key: same model, prompt version and input give the same key."""
    return hashlib.sha256("\x1f".join((model, prompt_version, system, user)).encode()).hexdigest()


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith(_JSON_FENCE[0]):
        t = t[len(_JSON_FENCE[0]):]
    elif t.startswith(_JSON_FENCE[1]):
        t = t[len(_JSON_FENCE[1]):]
    if t.endswith(_JSON_FENCE[1]):
        t = t[: -len(_JSON_FENCE[1])]
    return t.strip()


class LlmClient:
    """Shared by every live agent; one instance per process."""

    def __init__(self, providers: dict[str, LLMProvider], limits: LimitsConfig, cache: CachePort | None, clock: Clock) -> None:
        self._providers, self._limits, self._cache, self._clock = providers, limits, cache, clock
        self._sem = asyncio.Semaphore(limits.max_concurrency)

    def has(self, provider: str) -> bool:
        """True when a provider is configured (its API key is set)."""
        return provider in self._providers

    async def structured(self, route: AgentModelConfig, prompt_version: str, system: str, user: str, schema: type[SchemaT]) -> tuple[SchemaT, CallMeta]:
        """Return validated output of ``schema`` and the call cost.

        Tries ``route.model`` first, then ``route.fallback_model`` (same provider).
        The cache key uses the primary model so a re-run hits the cache whichever
        model answered; ``meta.model`` and ``llm_cache.model`` hold the answering model.

        Raises:
            LLMUnavailable: Provider missing, or no model answered with valid output.
        """
        meta = CallMeta(model=route.model, prompt_version=prompt_version)
        provider = self._providers.get(route.provider.value)
        if provider is None:
            reason = f"{route.provider.value}/{route.model}: provider is not configured"
            raise LLMUnavailable(reason, detail={"errors": [reason]})
        budget = self._limits.node_budget_seconds
        try:
            async with asyncio.timeout(budget) as scope:
                deadline = scope.when() or 0.0
                return await self._structured_in_budget(provider, route, prompt_version, system, user, schema, meta, deadline)
        except TimeoutError as exc:
            meta.errors.append(f"{provider.name}/{route.model}: node budget {budget:g}s spent")
            raise LLMUnavailable(f"{provider.name}/{route.model}: node budget {budget:g}s spent", detail={"errors": meta.errors}) from exc

    async def _structured_in_budget(self, provider: LLMProvider, route: AgentModelConfig, prompt_version: str, system: str, user: str, schema: type[SchemaT], meta: CallMeta, deadline: float) -> tuple[SchemaT, CallMeta]:
        """Cache lookup, then each model in turn; runs inside the node budget."""
        key = cache_key(route.model, prompt_version, system, user)
        if self._cache is not None and (hit := await self._cache.get(key)):
            meta.cache_hit = True
            return schema.model_validate(hit["response"]), meta

        models = [route.model] + ([route.fallback_model] if route.fallback_model else [])
        for model in models:
            parsed = await self._try_model(provider, route, model, system, user, schema, meta, deadline)
            if parsed is None:
                continue
            if self._cache is not None:
                await self._cache.put(key, model=meta.model, prompt_version=prompt_version, response=parsed.model_dump(mode="json"), tokens={"in": meta.tokens_in, "out": meta.tokens_out}, now=self._clock.now())
            return parsed, meta
        raise LLMUnavailable(f"{provider.name}/{models[-1]}: no model answered", detail={"errors": meta.errors})

    async def _try_model(self, provider: LLMProvider, route: AgentModelConfig, model: str, system: str, user: str, schema: type[SchemaT], meta: CallMeta, deadline: float) -> SchemaT | None:
        """Run the call and repair loop on one model; ``None`` means try the next model.

        Errors are appended to ``meta.errors`` with a ``provider/model`` prefix.
        """
        message = user
        for attempt in range(self._limits.repair_attempts + 1):
            request = LlmRequest(system, message, model, route.temperature or 0.0, route.max_tokens)
            try:
                text = await self._call(provider, request, meta, deadline)
            except LLMUnavailable:
                return None
            try:
                parsed = schema.model_validate(json.loads(_strip_fence(text)))
            except (json.JSONDecodeError, ValidationError) as exc:
                meta.errors.append(f"{provider.name}/{model}: invalid output (attempt {attempt + 1}): {str(exc)[:160]}")
                message = f"{user}\n\nYour previous answer was not valid JSON for the schema: {str(exc)[:400]}\nReturn only the corrected JSON object."
                continue
            meta.model = model
            return parsed
        return None

    async def _call(self, provider: LLMProvider, request: LlmRequest, meta: CallMeta, deadline: float) -> str:
        """One call with at most ``max_attempts`` tries; ``deadline`` is the node budget end.

        The call limit starts after the semaphore is taken, so waiting for a
        slot never shortens it (the node budget still covers the wait).

        Raises:
            LLMUnavailable: Timeout, non-retryable error, attempts used up, or a
                ``Retry-After`` longer than the backoff cap or the remaining budget.
        """
        label = f"{provider.name}/{request.model}"
        call_limit = self._limits.call_timeout_seconds
        backoff_cap = self._limits.backoff_max_seconds
        delay = self._limits.backoff_base_seconds
        last_attempt = self._limits.max_attempts - 1
        loop = asyncio.get_running_loop()
        for attempt in range(self._limits.max_attempts):
            try:
                async with self._sem:
                    async with asyncio.timeout(call_limit):
                        resp = await provider.complete(request)
                meta.tokens_in += resp.tokens_in
                meta.tokens_out += resp.tokens_out
                return resp.text
            except TimeoutError as exc:
                # A second wait on a slow model would leave no time for the fallback model.
                meta.errors.append(f"{label}: timeout after {call_limit:g}s")
                raise LLMUnavailable(f"{label}: timeout after {call_limit:g}s") from exc
            except ProviderError as exc:
                meta.errors.append(f"{label}: {exc}"[:ERROR_MAX])
                remaining = deadline - loop.time()
                too_long = exc.retry_after is not None and (exc.retry_after > backoff_cap or exc.retry_after > remaining)
                wait = min(exc.retry_after if exc.retry_after is not None else delay, backoff_cap)
                if not exc.retryable or attempt == last_attempt or too_long or wait >= remaining:
                    # Not retryable, out of attempts, or waiting is not worth it: next model.
                    raise LLMUnavailable(f"{label} failed: {exc}"[:ERROR_MAX]) from exc
                meta.retries += 1
                _logger.warning("llm retry", extra={"provider": provider.name, "attempt": attempt + 1, "wait_s": wait})
                await asyncio.sleep(wait)
                delay = min(delay * 2, backoff_cap)
        raise LLMUnavailable(f"{label} failed")

    async def aclose(self) -> None:
        for p in self._providers.values():
            await p.aclose()
