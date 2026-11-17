"""Unit tests for ``SystemService`` and ``MongoHealthProbe`` failure mapping.

The service is exercised with small in-test implementations of the
``HealthProbe`` port (it depends on the port, not on MongoDB). The probe's
failure path uses a real ``AsyncMongoClient`` pointed at a closed local port,
so no server is needed and nothing is mocked.

**Validates: Requirements 4.2, 4.3, 4.4, 5.2, 5.5**
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from pymongo import AsyncMongoClient

from backend.app.core.errors import DependencyUnavailable
from backend.app.domain.enums import HealthState, LlmMode
from backend.app.repositories.interfaces.health_probe import HealthProbe
from backend.app.repositories.mongo.health_probe import MongoHealthProbe
from backend.app.services.system_service import (
    HealthStatus,
    ProviderStatus,
    SystemService,
    SystemSettingsView,
)

pytestmark = pytest.mark.unit

_UNREACHABLE_HOST = "127.0.0.1"
_UNREACHABLE_PORT = 1
_SHORT_TIMEOUT_MS = 200


class _OkProbe:
    async def ping(self) -> None:
        return None


class _DownProbe:
    async def ping(self) -> None:
        raise DependencyUnavailable("MongoDB operational database is unreachable")


def _view(
    mode: LlmMode = LlmMode.FALLBACK, *, groq: bool = False, gemini: bool = False
) -> SystemSettingsView:
    return SystemSettingsView(
        llm_mode=mode,
        graph_version="0.1.0",
        config_versions={"llm": "0.1.0"},
        groq_key_configured=groq,
        gemini_key_configured=gemini,
    )


def _service(probe: HealthProbe, view: SystemSettingsView | None = None) -> SystemService:
    return SystemService(probe, view or _view())


async def test_check_health_ok() -> None:
    result = await _service(_OkProbe()).check_health()
    assert result == HealthStatus(status=HealthState.OK, db=HealthState.OK)


async def test_check_health_propagates_dependency_unavailable() -> None:
    with pytest.raises(DependencyUnavailable):
        await _service(_DownProbe()).check_health()


@pytest.mark.parametrize("mode", list(LlmMode))
@pytest.mark.parametrize("groq", [True, False])
@pytest.mark.parametrize("gemini", [True, False])
def test_public_config_matrix(mode: LlmMode, groq: bool, gemini: bool) -> None:
    cfg = _service(_OkProbe(), _view(mode, groq=groq, gemini=gemini)).public_config()
    live = mode is LlmMode.LIVE
    assert cfg.llm_mode is mode
    assert cfg.graph_version == "0.1.0"
    assert dict(cfg.config_versions) == {"llm": "0.1.0"}
    assert cfg.fallback_active is (mode is LlmMode.FALLBACK)
    assert cfg.providers.groq == ProviderStatus(configured=groq, active=live and groq)
    assert cfg.providers.gemini == ProviderStatus(configured=gemini, active=live and gemini)


def test_public_config_carries_no_secret_fields() -> None:
    cfg = _service(_OkProbe(), _view(LlmMode.LIVE, groq=True, gemini=True)).public_config()
    names = {f.name for f in dataclasses.fields(cfg)}
    names |= {f.name for f in dataclasses.fields(cfg.providers.groq)}
    assert not any("key" in n or "secret" in n for n in names), names


def test_settings_view_is_immutable() -> None:
    source = {"llm": "0.1.0"}
    view = _view()
    view = dataclasses.replace(view, config_versions=source)
    source["llm"] = "changed"
    assert view.config_versions["llm"] == "0.1.0"
    with pytest.raises(TypeError):
        view.config_versions["llm"] = "x"  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.graph_version = "x"  # type: ignore[misc]


async def test_mongo_probe_maps_unreachable_to_dependency_unavailable() -> None:
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
        host=_UNREACHABLE_HOST,
        port=_UNREACHABLE_PORT,
        serverSelectionTimeoutMS=_SHORT_TIMEOUT_MS,
        connectTimeoutMS=_SHORT_TIMEOUT_MS,
    )
    try:
        with pytest.raises(DependencyUnavailable) as info:
            await MongoHealthProbe(client["mulescope_unreachable"]).ping()
    finally:
        await client.close()
    err = info.value
    rendered = f"{err.message} {err.detail!r}"
    assert _UNREACHABLE_HOST not in rendered
    assert isinstance(err.detail, dict)
    assert err.detail["dependency"] == "mongodb"
