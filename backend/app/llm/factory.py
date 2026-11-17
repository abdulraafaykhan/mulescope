"""Builds the agent suite for a process from the LLM mode, config and keys.

Called by ``core/wiring.py`` (API, smoke and evals all go through it). In
fallback mode, or in live mode with no keys at all, it returns the template
suite and makes no network calls.
"""

from __future__ import annotations

from typing import Any

from backend.app.agents.suite import AgentSuite, build_live_suite
from backend.app.core.clock import Clock
from backend.app.core.config_files import LlmConfig
from backend.app.core.logging import get_logger
from backend.app.llm.client import LlmClient
from backend.app.llm.http_providers import GeminiProvider, GroqProvider
from backend.app.llm.provider import LLMProvider

_logger = get_logger(__name__)


def build_agent_suite(*, llm_mode: str, cfg: LlmConfig, groq_key: str | None, gemini_key: str | None, cache: Any, clock: Clock, str_sections: list[str], tipping_terms: list[str]) -> AgentSuite:
    """Return the template suite (fallback) or the live suite (live with keys)."""
    if llm_mode != "live":
        return AgentSuite()
    # Safety net only: LlmClient enforces the wall-clock limit with asyncio.timeout.
    timeout = cfg.limits.call_timeout_seconds
    providers: dict[str, LLMProvider] = {}
    if groq_key:
        providers["groq"] = GroqProvider(groq_key, cfg.providers.groq.base_url, timeout)
    if gemini_key:
        providers["gemini"] = GeminiProvider(gemini_key, cfg.providers.gemini.base_url, timeout)
    if not providers:
        _logger.warning("LLM_MODE=live but no GROQ_API_KEY or GEMINI_API_KEY is set; using template agents")
        return AgentSuite()
    client = LlmClient(providers, cfg.limits, cache, clock)
    return build_live_suite(client, cfg, str_sections, tipping_terms)
