"""Typed loader for the ``config/*.yaml`` files.

Section 10.2 of the build prompt keeps thresholds, weights, model names and
limits out of code. They live in YAML under ``config/`` and are loaded here with
``yaml.safe_load`` and validated into small, frozen Pydantic v2 models, so every
caller gets typed values instead of raw dictionaries.

M0 ships only :class:`LlmConfig` (``config/llm.yaml``). Later milestones add
models for ``scoring.yaml``, ``playbook.yaml`` and ``scenarios.yaml`` through the
same :func:`load_yaml_model` helper.

Called by the composition root (``backend/app/core/container.py``) and the
app factory at startup, and by the ``datagen`` and ``evals`` CLIs. Loading is
synchronous file I/O and is meant to run once at process start, before the
event loop serves requests.

Every failure (missing file, unreadable file, invalid YAML, schema mismatch)
raises :class:`~backend.app.core.errors.DependencyUnavailable` with a message
that names the file, so a misconfigured deployment fails fast and clearly.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.core.errors import DependencyUnavailable
from backend.app.domain.policy.config import PlaybookConfig, ScoringConfig

__all__ = [
    "LLM_CONFIG_FILENAME",
    "AgentModelConfig",
    "AgentsConfig",
    "CacheConfig",
    "LimitsConfig",
    "LlmConfig",
    "LlmProvider",
    "ModelPriceConfig",
    "ObservabilityConfig",
    "ProviderConfig",
    "ProvidersConfig",
    "load_llm_config",
    "load_yaml_model",
]

LLM_CONFIG_FILENAME = "llm.yaml"
"""File name of the LLM configuration inside the config directory."""


class LlmProvider(StrEnum):
    """LLM providers an agent can be routed to (build prompt section 2)."""

    GROQ = "groq"
    GEMINI = "gemini"


class _ConfigModel(BaseModel):
    """Base for config models: immutable and strict about unknown keys.

    Unknown keys are rejected so a typo in a YAML file is reported instead of
    being silently ignored.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class ProviderConfig(_ConfigModel):
    """Connection-independent settings for one LLM provider.

    API keys are never part of this model; they come from the environment.

    Attributes:
        default_model: Model name used when an agent does not override it.
    """

    default_model: str = Field(min_length=1)
    base_url: str = Field(min_length=1)


class ProvidersConfig(_ConfigModel):
    """Per-provider settings keyed by provider name.

    Attributes:
        groq: Groq provider settings.
        gemini: Gemini provider settings.
    """

    groq: ProviderConfig
    gemini: ProviderConfig


class AgentModelConfig(_ConfigModel):
    """Model routing for a single agent.

    Attributes:
        provider: Provider that serves this agent.
        model: Primary model name at that provider.
        fallback_model: Optional second model at the same provider, tried when the
            primary fails or returns invalid output, before the template fallback.
        temperature: Sampling temperature, or ``None`` while still a placeholder.
        reasoning_effort: Groq ``reasoning_effort`` for gpt-oss models (``low``,
            ``medium`` or ``high``). ``None`` leaves the provider default. Ignored
            by Gemini.
    """

    provider: LlmProvider
    model: str = Field(min_length=1)
    fallback_model: str | None = Field(default=None, min_length=1)
    temperature: float | None = Field(default=None, ge=0)
    max_tokens: int = Field(default=1500, gt=0)
    reasoning_effort: Literal["low", "medium", "high"] | None = None


class AgentsConfig(_ConfigModel):
    """Model routing for every agent in the graph.

    Attributes:
        profiler: Profiler agent routing.
        flow_analyst: Flow Analyst agent routing.
        narrative_writer: Narrative Writer agent routing.
        critic: Critic agent routing.
    """

    profiler: AgentModelConfig
    flow_analyst: AgentModelConfig
    narrative_writer: AgentModelConfig
    critic: AgentModelConfig


class CacheConfig(_ConfigModel):
    """LLM response cache settings.

    Attributes:
        ttl_days: Retention of ``llm_cache`` documents, in days.
    """

    ttl_days: int = Field(gt=0)


class LimitsConfig(_ConfigModel):
    """Free-tier protection: concurrency, timeouts and retry policy.

    Attributes:
        max_concurrency: Global semaphore size across all LLM calls.
        call_timeout_seconds: Wall-clock limit for one provider call. It starts
            after the semaphore is taken, so queueing does not eat into it.
        max_attempts: Attempts per call and model (first try plus retries) on
            rate limits and 5xx. A timeout is never retried on the same model.
        node_budget_seconds: Wall-clock limit for one structured call, covering
            every attempt, the fallback model and the repair attempt.
        backoff_base_seconds: First backoff delay; doubles per retry.
        backoff_max_seconds: Upper bound for one backoff delay. A longer
            ``Retry-After`` moves on to the next model instead of waiting.
        repair_attempts: Extra calls when the output fails schema validation.
    """

    max_concurrency: int = Field(default=2, gt=0)
    call_timeout_seconds: float = Field(default=20, gt=0)
    max_attempts: int = Field(default=2, gt=0)
    node_budget_seconds: float = Field(default=40, gt=0)
    backoff_base_seconds: float = Field(default=2, ge=0)
    backoff_max_seconds: float = Field(default=5, ge=0)
    repair_attempts: int = Field(default=1, ge=0)


class ModelPriceConfig(_ConfigModel):
    """List price and free-tier rate limit of one model, for estimates only.

    Attributes:
        input_usd_per_million: USD per million prompt tokens.
        output_usd_per_million: USD per million completion tokens.
        tokens_per_minute: Free-tier tokens-per-minute limit, or ``None`` when unknown.
    """

    input_usd_per_million: float = Field(ge=0)
    output_usd_per_million: float = Field(ge=0)
    tokens_per_minute: int | None = Field(default=None, gt=0)


class ObservabilityConfig(_ConfigModel):
    """LLM call log settings.

    Attributes:
        call_log_ttl_days: Retention of ``llm_calls`` documents, in days.
    """

    call_log_ttl_days: int = Field(gt=0)


class LlmConfig(_ConfigModel):
    """Validated contents of ``config/llm.yaml``.

    Attributes:
        version: Config version, reported by ``/api/v1/config/public``.
        providers: Per-provider settings.
        agents: Per-agent model routing.
        cache: LLM response cache settings.
        models: Price and rate limit per model name. A model missing here has
            no estimated cost.
        observability: LLM call log settings.
    """

    version: str = Field(min_length=1)
    providers: ProvidersConfig
    agents: AgentsConfig
    limits: LimitsConfig = LimitsConfig()
    cache: CacheConfig
    models: dict[str, ModelPriceConfig] = Field(default_factory=dict)
    observability: ObservabilityConfig

    @property
    def cache_ttl_seconds(self) -> int:
        """Return the ``llm_cache`` TTL in seconds, derived from ``cache.ttl_days``.

        This is the value passed to the ``llm_cache`` ``created_at`` TTL index.

        Returns:
            The cache retention in whole seconds.
        """
        return int(timedelta(days=self.cache.ttl_days).total_seconds())

    @property
    def call_log_ttl_seconds(self) -> int:
        """Return the ``llm_calls`` TTL in seconds, from ``observability.call_log_ttl_days``."""
        return int(timedelta(days=self.observability.call_log_ttl_days).total_seconds())


def load_yaml_model[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    """Load one YAML file and validate it into ``model``.

    Args:
        path: Path to the YAML file.
        model: Pydantic model class the document must satisfy.

    Returns:
        The validated model instance.

    Raises:
        DependencyUnavailable: If the file is missing, unreadable, not valid
            YAML, not a mapping at the top level, or fails validation.
    """
    detail: dict[str, Any] = {"path": str(path)}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DependencyUnavailable(f"Config file not found: {path}", detail=detail) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise DependencyUnavailable(
            f"Config file could not be read: {path} ({exc})", detail=detail
        ) from exc

    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DependencyUnavailable(
            f"Config file is not valid YAML: {path} ({exc})", detail=detail
        ) from exc

    if not isinstance(raw, dict):
        raise DependencyUnavailable(
            f"Config file must contain a YAML mapping at the top level: {path}",
            detail=detail,
        )

    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        errors = [
            {"loc": ".".join(str(part) for part in err["loc"]), "msg": err["msg"]}
            for err in exc.errors()
        ]
        raise DependencyUnavailable(
            f"Config file failed validation: {path} ({exc.error_count()} error(s))",
            detail={**detail, "errors": errors},
        ) from exc


def load_scoring_config(config_dir: Path) -> ScoringConfig:
    """Load ``scoring.yaml`` (detector, metrics, signals, policy, typologies)."""
    return load_yaml_model(config_dir / "scoring.yaml", ScoringConfig)


def load_playbook_config(config_dir: Path) -> PlaybookConfig:
    """Load ``playbook.yaml`` (actions, rules, SLAs)."""
    return load_yaml_model(config_dir / "playbook.yaml", PlaybookConfig)


def load_scenarios_config(config_dir: Path) -> dict[str, Any]:
    """Load ``scenarios.yaml`` as a plain mapping (datagen parameters)."""
    path = config_dir / "scenarios.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DependencyUnavailable(f"Config file could not be loaded: {path}", detail={"path": str(path)}) from exc
    if not isinstance(raw, dict):
        raise DependencyUnavailable(f"Config file must be a mapping: {path}", detail={"path": str(path)})
    return raw


def load_llm_config(config_dir: Path) -> LlmConfig:
    """Load and validate ``llm.yaml`` from ``config_dir``.

    Args:
        config_dir: Directory holding the ``config/*.yaml`` files. Callers pass
            ``settings.config_dir``.

    Returns:
        The validated LLM configuration.

    Raises:
        DependencyUnavailable: If the file is missing or invalid.
    """
    return load_yaml_model(config_dir / LLM_CONFIG_FILENAME, LlmConfig)
