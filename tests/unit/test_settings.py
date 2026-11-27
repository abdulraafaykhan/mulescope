"""Unit tests for ``backend.app.core.settings``.

Hermetic: every settings object is built with ``_env_file=None`` and every
settings-related environment variable is cleared first, so no real ``.env``
file or shell variable can leak into the assertions.

Covers Property 7 (truth isolation by construction, settings part).

**Validates: Requirements 3.1, 3.2, 3.3**
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import SecretStr, ValidationError

from backend.app.core.settings import (
    ApiSettings,
    BaseAppSettings,
    DatagenSettings,
    EvalsSettings,
)
from backend.app.domain.enums import LlmMode

pytestmark = pytest.mark.unit

FAKE_MONGO_URI = "mongodb://test-host:27017"
FAKE_TRUTH_URI = "mongodb://truth-test-host:27017"
FAKE_SECRET_KEY = "fake-test-key-not-real"

_ALL_SETTINGS_CLASSES: tuple[type[BaseAppSettings], ...] = (
    BaseAppSettings,
    ApiSettings,
    DatagenSettings,
    EvalsSettings,
)
_TRUTH_FIELDS = ("mongo_truth_uri", "mongo_truth_db_name")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every settings-backed variable from the environment."""
    names = {name for cls in _ALL_SETTINGS_CLASSES for name in cls.model_fields}
    for name in names:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the minimum required variables with fake values."""
    monkeypatch.setenv("MONGO_URI", FAKE_MONGO_URI)
    monkeypatch.setenv("MONGO_TRUTH_URI", FAKE_TRUTH_URI)


def test_api_settings_has_no_truth_fields() -> None:
    for field in _TRUTH_FIELDS:
        assert field not in ApiSettings.model_fields
        assert field not in BaseAppSettings.model_fields


@pytest.mark.parametrize("cls", [DatagenSettings, EvalsSettings])
def test_datagen_and_evals_have_truth_fields(cls: type[BaseAppSettings]) -> None:
    for field in _TRUTH_FIELDS:
        assert field in cls.model_fields


@pytest.mark.usefixtures("base_env")
def test_api_settings_ignores_truth_uri_in_env() -> None:
    settings = ApiSettings(_env_file=None)
    assert not hasattr(settings, "mongo_truth_uri")
    assert "mongo_truth_uri" not in settings.model_dump()


@pytest.mark.usefixtures("base_env")
def test_defaults() -> None:
    settings = ApiSettings(_env_file=None)
    assert settings.mongo_uri.get_secret_value() == FAKE_MONGO_URI
    assert settings.mongo_db_name == "mulescope"
    assert settings.llm_mode is LlmMode.LIVE
    assert settings.checkpoint_ttl_days == 7
    assert settings.groq_api_key is None
    assert settings.gemini_api_key is None
    assert isinstance(settings.as_of_date, date)


@pytest.mark.usefixtures("base_env")
@pytest.mark.parametrize("cls", [DatagenSettings, EvalsSettings])
def test_truth_db_name_default(cls: type[DatagenSettings | EvalsSettings]) -> None:
    settings = cls(_env_file=None)
    assert settings.mongo_truth_uri.get_secret_value() == FAKE_TRUTH_URI
    assert settings.mongo_truth_db_name == "mulescope_truth"


@pytest.mark.parametrize("cls", [DatagenSettings, EvalsSettings])
def test_truth_uri_is_required(
    cls: type[DatagenSettings | EvalsSettings], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MONGO_URI", FAKE_MONGO_URI)
    with pytest.raises(ValidationError):
        cls(_env_file=None)


def test_mongo_uri_is_required() -> None:
    with pytest.raises(ValidationError):
        ApiSettings(_env_file=None)


@pytest.mark.usefixtures("base_env")
@pytest.mark.parametrize("days", [1, 7, 30])
def test_checkpoint_ttl_seconds(days: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHECKPOINT_TTL_DAYS", str(days))
    settings = ApiSettings(_env_file=None)
    assert settings.checkpoint_ttl_days == days
    assert settings.checkpoint_ttl_seconds == days * 86400
    assert settings.checkpoint_ttl_seconds == int(timedelta(days=days).total_seconds())


@pytest.mark.usefixtures("base_env")
def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_DB_NAME", "override_db")
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("AS_OF_DATE", "2026-01-15")
    monkeypatch.setenv("CHECKPOINT_TTL_DAYS", "3")
    monkeypatch.setenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "1234")
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("API_PORT", "9001")
    monkeypatch.setenv("GROQ_API_KEY", FAKE_SECRET_KEY)
    monkeypatch.setenv("MONGO_TRUTH_DB_NAME", "override_truth")

    api = ApiSettings(_env_file=None)
    assert api.mongo_db_name == "override_db"
    assert api.llm_mode is LlmMode.LIVE
    assert api.as_of_date == date(2026, 1, 15)
    assert api.checkpoint_ttl_days == 3
    assert api.mongo_server_selection_timeout_ms == 1234
    assert api.api_host == "0.0.0.0"
    assert api.api_port == 9001
    assert api.groq_api_key is not None
    assert api.groq_api_key.get_secret_value() == FAKE_SECRET_KEY

    datagen = DatagenSettings(_env_file=None)
    assert datagen.mongo_truth_db_name == "override_truth"


@pytest.mark.usefixtures("base_env")
def test_invalid_llm_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "sometimes")
    with pytest.raises(ValidationError):
        ApiSettings(_env_file=None)


@pytest.mark.usefixtures("base_env")
def test_secrets_do_not_leak_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", FAKE_SECRET_KEY)
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_SECRET_KEY)
    for settings in (
        ApiSettings(_env_file=None),
        DatagenSettings(_env_file=None),
    ):
        text = repr(settings) + str(settings)
        assert FAKE_SECRET_KEY not in text
        assert FAKE_MONGO_URI not in text
        assert FAKE_TRUTH_URI not in text
        assert isinstance(settings.mongo_uri, SecretStr)
