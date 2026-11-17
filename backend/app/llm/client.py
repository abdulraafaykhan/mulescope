"""Structured LLM calls: cache, global semaphore, retry with backoff, schema repair.

``LlmClient.structured`` is the only way agents reach a model:

1. Look up ``llm_cache`` by ``sha256(model, prompt_version, system, user)``.
2. Otherwise take the global semaphore (``limits.max_concurrency``), call the
   provider and retry retryable errors with exponential backoff.
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

        Raises:
            LLMUnavailable: Provider missing, retries exhausted or output invalid after repair.
        """
        meta = CallMeta(model=route.model, prompt_version=prompt_version)
        provider = self._providers.get(route.provider.value)
        if provider is None:
            raise LLMUnavailable(f"{route.provider.value} is not configured")
        key = cache_key(route.model, prompt_version, system, user)
        if self._cache is not None and (hit := await self._cache.get(key)):
            meta.cache_hit = True
            return schema.model_validate(hit["response"]), meta

        message = user
        for attempt in range(self._limits.repair_attempts + 1):
            text = await self._call(provider, LlmRequest(system, message, route.model, route.temperature or 0.0, route.max_tokens), meta)
            try:
                parsed = schema.model_validate(json.loads(_strip_fence(text)))
            except (json.JSONDecodeError, ValidationError) as exc:
                meta.errors.append(f"invalid output (attempt {attempt + 1}): {str(exc)[:160]}")
                message = f"{user}\n\nYour previous answer was not valid JSON for the schema: {str(exc)[:400]}\nReturn only the corrected JSON object."
                continue
            if self._cache is not None:
                await self._cache.put(key, model=route.model, prompt_version=prompt_version, response=parsed.model_dump(mode="json"), tokens={"in": meta.tokens_in, "out": meta.tokens_out}, now=self._clock.now())
            return parsed, meta
        raise LLMUnavailable("output did not match the schema after repair", detail={"errors": meta.errors})

    async def _call(self, provider: LLMProvider, request: LlmRequest, meta: CallMeta) -> str:
        delay = self._limits.backoff_base_seconds
        for attempt in range(self._limits.max_retries + 1):
            try:
                async with self._sem:
                    resp = await provider.complete(request)
                meta.tokens_in += resp.tokens_in
                meta.tokens_out += resp.tokens_out
                meta.model = resp.model
                return resp.text
            except ProviderError as exc:
                meta.errors.append(str(exc)[:200])
                if not exc.retryable or attempt == self._limits.max_retries:
                    raise LLMUnavailable(f"{provider.name} failed: {exc}"[:300]) from exc
                meta.retries += 1
                wait = min(exc.retry_after or delay, self._limits.backoff_max_seconds)
                _logger.warning("llm retry", extra={"provider": provider.name, "attempt": attempt + 1, "wait_s": wait})
                await asyncio.sleep(wait)
                delay = min(delay * 2, self._limits.backoff_max_seconds)
        raise LLMUnavailable(f"{provider.name} failed")

    async def aclose(self) -> None:
        for p in self._providers.values():
            await p.aclose()
