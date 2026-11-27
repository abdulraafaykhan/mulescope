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
5. Report every provider attempt and cache hit to the optional ``AttemptSink``
   (the ``llm_calls`` log behind the observability page).

On final failure it raises ``LLMUnavailable``; the agent then uses its
template implementation, so a run never fails because of an LLM.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from backend.app.core.clock import Clock
from backend.app.core.config_files import AgentModelConfig, LimitsConfig
from backend.app.core.errors import LLMUnavailable
from backend.app.core.logging import get_logger
from backend.app.domain.enums import LlmCallOutcome
from backend.app.llm.provider import LLMProvider, LlmRequest, LlmResponse, ProviderError
from backend.app.llm.telemetry import AttemptSink, LlmAttempt

SchemaT = TypeVar("SchemaT", bound=BaseModel)
_logger = get_logger(__name__)
_JSON_FENCE = ("```json", "```")
# Long enough to keep a Groq error code and a failed_generation excerpt.
ERROR_MAX = 700
MS_PER_SECOND = 1000


class CachePort(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def put(self, key: str, *, model: str, prompt_version: str, response: dict[str, Any], tokens: dict[str, int], now: Any) -> None: ...


@dataclass
class CallMeta:
    """What one structured call cost; merged into the node's ``_node_meta``.

    ``call_id``, ``attempts``, ``current_model`` and ``inflight_since`` are
    bookkeeping for the attempt log and are not part of ``as_meta``.
    """

    model: str
    prompt_version: str
    tokens_in: int = 0
    tokens_out: int = 0
    retries: int = 0
    cache_hit: bool = False
    errors: list[str] = field(default_factory=list)
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempts: int = 0
    current_model: str = ""
    inflight_since: float | None = None

    def as_meta(self) -> dict[str, Any]:
        return {"model": self.model, "prompt_version": self.prompt_version, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "retries": self.retries, "cache_hit": self.cache_hit}


def cache_key(model: str, prompt_version: str, system: str, user: str) -> str:
    """Stable key: same model, prompt version and input give the same key."""
    return hashlib.sha256("\x1f".join((model, prompt_version, system, user)).encode()).hexdigest()


def _elapsed_ms(loop: asyncio.AbstractEventLoop, since: float) -> int:
    return int((loop.time() - since) * MS_PER_SECOND)


def _provider_outcome(exc: ProviderError) -> LlmCallOutcome:
    if exc.status == HTTPStatus.TOO_MANY_REQUESTS:
        return LlmCallOutcome.RATE_LIMITED
    return LlmCallOutcome.PROVIDER_ERROR


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

    def __init__(
        self,
        providers: dict[str, LLMProvider],
        limits: LimitsConfig,
        cache: CachePort | None,
        clock: Clock,
        sink: AttemptSink | None = None,
    ) -> None:
        self._providers, self._limits, self._cache, self._clock = providers, limits, cache, clock
        self._sink = sink
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
        meta = CallMeta(model=route.model, prompt_version=prompt_version, current_model=route.model)
        provider = self._providers.get(route.provider.value)
        if provider is None:
            reason = f"{route.provider.value}/{route.model}: provider is not configured"
            raise LLMUnavailable(reason, detail={"errors": [reason]})
        budget = self._limits.node_budget_seconds
        loop = asyncio.get_running_loop()
        try:
            async with asyncio.timeout(budget) as scope:
                deadline = scope.when() or 0.0
                return await self._structured_in_budget(provider, route, prompt_version, system, user, schema, meta, deadline)
        except TimeoutError as exc:
            reason = f"{provider.name}/{meta.current_model}: node budget {budget:g}s spent"
            meta.errors.append(reason)
            # The budget can expire mid-call; that attempt is recorded here.
            since = meta.inflight_since
            latency = _elapsed_ms(loop, since) if since is not None else 0
            await self._record(
                meta, provider.name, meta.current_model, LlmCallOutcome.BUDGET_EXCEEDED, latency,
                error=reason,
            )
            raise LLMUnavailable(reason, detail={"errors": meta.errors}) from exc

    async def _structured_in_budget(self, provider: LLMProvider, route: AgentModelConfig, prompt_version: str, system: str, user: str, schema: type[SchemaT], meta: CallMeta, deadline: float) -> tuple[SchemaT, CallMeta]:
        """Cache lookup, then each model in turn; runs inside the node budget."""
        key = cache_key(route.model, prompt_version, system, user)
        loop = asyncio.get_running_loop()
        started = loop.time()
        if self._cache is not None and (hit := await self._cache.get(key)):
            meta.cache_hit = True
            meta.attempts += 1
            saved = hit.get("tokens") or {}
            cached_model = str(hit.get("model") or route.model)
            await self._record(
                meta, provider.name, cached_model, LlmCallOutcome.CACHE_HIT, _elapsed_ms(loop, started),
                saved_in=int(saved.get("in", 0)), saved_out=int(saved.get("out", 0)),
            )
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
        meta.current_model = model
        for attempt in range(self._limits.repair_attempts + 1):
            request = LlmRequest(system, message, model, route.temperature or 0.0, route.max_tokens, route.reasoning_effort)
            try:
                resp, latency = await self._call(provider, request, meta, deadline)
            except LLMUnavailable:
                return None
            try:
                parsed = schema.model_validate(json.loads(_strip_fence(resp.text)))
            except (json.JSONDecodeError, ValidationError) as exc:
                reason = (
                    f"{provider.name}/{model}: invalid output (attempt {attempt + 1}): {str(exc)[:160]}"
                )
                meta.errors.append(reason)
                await self._record(
                    meta, provider.name, model, LlmCallOutcome.INVALID_OUTPUT, latency,
                    resp=resp, error=reason,
                )
                message = f"{user}\n\nYour previous answer was not valid JSON for the schema: {str(exc)[:400]}\nReturn only the corrected JSON object."
                continue
            await self._record(meta, provider.name, model, LlmCallOutcome.OK, latency, resp=resp)
            meta.model = model
            return parsed
        return None

    async def _call(
        self, provider: LLMProvider, request: LlmRequest, meta: CallMeta, deadline: float
    ) -> tuple[LlmResponse, int]:
        """One call with at most ``max_attempts`` tries; ``deadline`` is the node budget end.

        The call limit starts after the semaphore is taken, so waiting for a
        slot never shortens it (the node budget still covers the wait).
        Failed attempts are recorded here; the caller records the successful
        one once it knows whether the output validates.

        Returns:
            The provider response and its latency in milliseconds.

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
            meta.attempts += 1
            try:
                async with self._sem:
                    started = meta.inflight_since = loop.time()
                    async with asyncio.timeout(call_limit):
                        resp = await provider.complete(request)
                meta.inflight_since = None
                meta.tokens_in += resp.tokens_in
                meta.tokens_out += resp.tokens_out
                return resp, _elapsed_ms(loop, started)
            except TimeoutError as exc:
                meta.inflight_since = None
                # A second wait on a slow model would leave no time for the fallback model.
                reason = f"{label}: timeout after {call_limit:g}s"
                meta.errors.append(reason)
                latency = _elapsed_ms(loop, started)
                await self._record(
                    meta, provider.name, request.model, LlmCallOutcome.TIMEOUT, latency, error=reason
                )
                raise LLMUnavailable(reason) from exc
            except ProviderError as exc:
                meta.inflight_since = None
                meta.errors.append(f"{label}: {exc}"[:ERROR_MAX])
                await self._record(
                    meta, provider.name, request.model, _provider_outcome(exc),
                    _elapsed_ms(loop, started), error=str(exc)[:ERROR_MAX],
                )
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

    async def _record(
        self,
        meta: CallMeta,
        provider: str,
        model: str,
        outcome: LlmCallOutcome,
        latency_ms: int,
        *,
        resp: LlmResponse | None = None,
        error: str | None = None,
        saved_in: int = 0,
        saved_out: int = 0,
    ) -> None:
        """Report one attempt to the sink, numbered by ``meta.attempts``."""
        if self._sink is None:
            return
        attempt = LlmAttempt(
            call_id=meta.call_id,
            provider=provider,
            model=model,
            prompt_version=meta.prompt_version,
            attempt=meta.attempts,
            outcome=outcome,
            latency_ms=latency_ms,
            tokens_in=resp.tokens_in if resp else 0,
            tokens_out=resp.tokens_out if resp else 0,
            saved_tokens_in=saved_in,
            saved_tokens_out=saved_out,
            error=error,
        )
        await self._sink.record(attempt)

    async def aclose(self) -> None:
        for p in self._providers.values():
            await p.aclose()
