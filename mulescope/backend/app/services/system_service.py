"""System use cases: health check and public configuration.

Built by ``core.container`` and called by the ``/health`` and
``/api/v1/config/public`` routers. The service depends only on the
:class:`~backend.app.repositories.interfaces.health_probe.HealthProbe` port and
the domain enums. It never sees settings classes or secret values: the
container hands it a :class:`SystemSettingsView` holding plain, non-secret
facts (mode, versions and whether each provider key is configured).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from backend.app.domain.enums import HealthState, LlmMode
from backend.app.repositories.interfaces.health_probe import HealthProbe

__all__ = [
    "HealthStatus",
    "ProviderStatus",
    "ProvidersStatus",
    "PublicConfig",
    "SystemService",
    "SystemSettingsView",
]


def _freeze(mapping: Mapping[str, str]) -> Mapping[str, str]:
    """Return a read-only copy of ``mapping``."""
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True, slots=True)
class SystemSettingsView:
    """The non-secret settings facts the system service needs.

    Attributes:
        llm_mode: Configured LLM mode.
        graph_version: Version of the investigation graph code.
        config_versions: Config file name to its ``version`` value, for
            example ``{"llm": "0.1.0"}``. Stored as a read-only copy.
        groq_key_configured: Whether a Groq API key is set.
        gemini_key_configured: Whether a Gemini API key is set.
    """

    llm_mode: LlmMode
    graph_version: str
    config_versions: Mapping[str, str]
    groq_key_configured: bool
    gemini_key_configured: bool

    def __post_init__(self) -> None:
        """Replace ``config_versions`` with a read-only copy."""
        object.__setattr__(self, "config_versions", _freeze(self.config_versions))


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Result of a successful health check.

    Attributes:
        status: Overall service health.
        db: Operational database health.
    """

    status: HealthState
    db: HealthState


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """Public status of one LLM provider. Never carries the key itself.

    Attributes:
        configured: Whether an API key is set for the provider.
        active: Whether agents will call it (key configured and live mode).
    """

    configured: bool
    active: bool


@dataclass(frozen=True, slots=True)
class ProvidersStatus:
    """Public status of every LLM provider.

    Attributes:
        groq: Groq provider status.
        gemini: Gemini provider status.
    """

    groq: ProviderStatus
    gemini: ProviderStatus


@dataclass(frozen=True, slots=True)
class PublicConfig:
    """Configuration safe to expose to any client.

    Attributes:
        llm_mode: Configured LLM mode.
        graph_version: Version of the investigation graph code.
        config_versions: Config file name to its ``version`` value.
        providers: Per-provider status, without key values.
        fallback_active: ``True`` when agents use the deterministic fallback
            provider, i.e. when ``llm_mode`` is ``fallback``.
    """

    llm_mode: LlmMode
    graph_version: str
    config_versions: Mapping[str, str]
    providers: ProvidersStatus
    fallback_active: bool


class SystemService:
    """Health and public-config use cases.

    Args:
        probe: Liveness check for the operational datastore.
        settings_view: Non-secret settings facts.
    """

    def __init__(self, probe: HealthProbe, settings_view: SystemSettingsView) -> None:
        """Store collaborators.

        Args:
            probe: Liveness check for the operational datastore.
            settings_view: Non-secret settings facts.
        """
        self._probe = probe
        self._view = settings_view

    async def check_health(self) -> HealthStatus:
        """Ping the datastore and report health.

        Returns:
            ``HealthStatus`` with ``status`` and ``db`` both ``ok``.

        Raises:
            DependencyUnavailable: If the datastore ping fails. It is never
                swallowed, so the API returns 503 rather than a false 200.
        """
        await self._probe.ping()
        return HealthStatus(status=HealthState.OK, db=HealthState.OK)

    def public_config(self) -> PublicConfig:
        """Return configuration that is safe to show to any client.

        Returns:
            Mode, versions and provider status. Key values are never included.
        """
        view = self._view
        live = view.llm_mode is LlmMode.LIVE
        return PublicConfig(
            llm_mode=view.llm_mode,
            graph_version=view.graph_version,
            config_versions=_freeze(view.config_versions),
            providers=ProvidersStatus(
                groq=ProviderStatus(
                    configured=view.groq_key_configured,
                    active=live and view.groq_key_configured,
                ),
                gemini=ProviderStatus(
                    configured=view.gemini_key_configured,
                    active=live and view.gemini_key_configured,
                ),
            ),
            fallback_active=view.llm_mode is LlmMode.FALLBACK,
        )
