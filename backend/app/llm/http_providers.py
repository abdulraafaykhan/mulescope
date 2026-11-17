"""Groq and Gemini providers over their HTTPS JSON APIs (httpx, async).

Groq exposes an OpenAI-compatible chat endpoint; we ask for a JSON object.
Gemini's ``generateContent`` is asked for ``application/json``. Both map HTTP
429, 408 and 5xx (and transport errors) to a retryable ``ProviderError`` and
honour ``Retry-After``. A timeout is a non-retryable ``ProviderError``. Base
URLs come from ``config/llm.yaml``; keys from settings.
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.app.llm.provider import LlmRequest, LlmResponse, ProviderError

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
ERROR_BODY_MAX = 200
MESSAGE_MAX = 120
FAILED_GENERATION_MAX = 400


def _error_text(resp: httpx.Response) -> str:
    """Short error text: status, provider error code, message and a ``failed_generation`` excerpt.

    Why: Groq answers HTTP 400 ``json_validate_failed`` with the rejected
    model output in ``failed_generation``; a plain prefix of the body cut it
    off and made the cause invisible. Never includes the request or the key.
    """
    try:
        error = resp.json()["error"]
        code = error.get("code") or error.get("type") or ""
        head = f"HTTP {resp.status_code} {code}".strip() + f": {str(error.get('message', ''))[:MESSAGE_MAX]}"
        failed = error.get("failed_generation")
        return f"{head}; failed_generation: {str(failed)[:FAILED_GENERATION_MAX]!r}" if failed else head
    except (ValueError, KeyError, TypeError, AttributeError):
        return f"HTTP {resp.status_code}: {resp.text[:ERROR_BODY_MAX]}"


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("retry-after")
    try:
        return float(value) if value else None
    except ValueError:
        return None


async def _post(client: httpx.AsyncClient, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    try:
        resp = await client.post(url, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        # Not retryable: LlmClient moves to the next model after a timeout.
        raise ProviderError(f"timeout: {type(exc).__name__}", retryable=False) from exc
    except httpx.TransportError as exc:
        raise ProviderError(f"transport error: {type(exc).__name__}", retryable=True) from exc
    if resp.status_code >= 400:
        # Error bodies can be long; keep the start for diagnostics, never the request.
        raise ProviderError(_error_text(resp), retryable=resp.status_code in RETRYABLE_STATUS, retry_after=_retry_after(resp))
    data: dict[str, Any] = resp.json()
    return data


class GroqProvider:
    """Groq chat completions (OpenAI-compatible) with JSON-object output."""

    name = "groq"

    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
        self._key = api_key
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._client = httpx.AsyncClient(timeout=timeout)

    async def complete(self, request: LlmRequest) -> LlmResponse:
        body = {
            "model": request.model,
            "messages": [{"role": "system", "content": request.system}, {"role": "user", "content": request.user}],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_tokens,
            "response_format": {"type": "json_object"},
        }
        data = await _post(self._client, self._url, body, {"Authorization": f"Bearer {self._key}"})
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("unexpected Groq response shape", retryable=False) from exc
        usage = data.get("usage") or {}
        return LlmResponse(text=text, tokens_in=int(usage.get("prompt_tokens", 0)), tokens_out=int(usage.get("completion_tokens", 0)), model=str(data.get("model", request.model)))

    async def aclose(self) -> None:
        await self._client.aclose()


class GeminiProvider:
    """Gemini ``generateContent`` with JSON output."""

    name = "gemini"

    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def complete(self, request: LlmRequest) -> LlmResponse:
        body = {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": [{"role": "user", "parts": [{"text": request.user}]}],
            "generationConfig": {"temperature": request.temperature, "maxOutputTokens": request.max_tokens, "responseMimeType": "application/json"},
        }
        url = f"{self._base}/models/{request.model}:generateContent"
        data = await _post(self._client, url, body, {"x-goog-api-key": self._key})
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        except (KeyError, IndexError, TypeError) as exc:
            reason = (data.get("promptFeedback") or {}).get("blockReason") or (data.get("candidates") or [{}])[0].get("finishReason")
            raise ProviderError(f"unexpected Gemini response (reason {reason})", retryable=False) from exc
        usage = data.get("usageMetadata") or {}
        out = int(usage.get("candidatesTokenCount", 0)) + int(usage.get("thoughtsTokenCount", 0))
        return LlmResponse(text=text, tokens_in=int(usage.get("promptTokenCount", 0)), tokens_out=out, model=str(data.get("modelVersion", request.model)))

    async def aclose(self) -> None:
        await self._client.aclose()
