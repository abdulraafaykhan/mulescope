"""Typed process settings for MuleScope, loaded from the environment.

Three entry-point processes exist, and each loads its own settings class so the
API can never reach the truth database (build prompt section 5):

* :class:`ApiSettings`: loaded by the API process (``uv run dev``) through the
  app factory and the composition root. It has **no** truth connection field.
* :class:`DatagenSettings`: loaded by ``uv run seed`` (``datagen/cli.py``). It
  adds the truth connection and is the only process that bootstraps it.
* :class:`EvalsSettings`: loaded by ``uv run evals`` (``evals/cli.py``). It adds
  the truth connection for read-only scoring.

Sources, lowest to highest precedence:

1. Field defaults in this module.
2. ``<repo root>/.env``, the single local env file.
3. Real environment variables (for example ``$env:LLM_MODE = "live"``).

The ``.env`` path is resolved from this file's location, not from the
current working directory, so ``uv run ...`` finds it from any folder. A
missing file is skipped. Unknown keys are ignored, which is what lets the
API process load a ``.env`` that also carries ``MONGO_TRUTH_URI`` without
ever exposing it.

Secrets (API keys and Mongo URIs, which may embed a password) are typed as
:class:`~pydantic.SecretStr`, so they never appear in ``repr`` output or logs.
Callers read them with ``.get_secret_value()`` at the point of use.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Final

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.domain.enums import LlmMode

__all__ = [
    "CONFIG_DIR",
    "DEFAULT_AS_OF_DATE",
    "ENV_FILES",
    "GRAPH_VERSION",
    "PROJECT_ROOT",
    "ApiSettings",
    "BaseAppSettings",
    "DatagenSettings",
    "EvalsSettings",
]

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
"""The repository root (``backend/app/core/settings.py`` -> 3 levels up)."""

ENV_FILES: Final[tuple[Path, ...]] = (PROJECT_ROOT / ".env",)
"""``.env`` files read in order (just the root one); missing files are skipped."""

CONFIG_DIR: Final[Path] = PROJECT_ROOT / "config"
"""Default directory of the ``config/*.yaml`` files."""

GRAPH_VERSION: Final[str] = "0.1.0"
"""Version of the investigation graph code, stamped on every case run.

It versions the code, not the deployment, so it is a constant and is not
read from the environment.
"""

DEFAULT_AS_OF_DATE: Final[date] = date.fromisoformat("2026-10-31")
"""Default dataset end date."""


class BaseAppSettings(BaseSettings):
    """Settings shared by every MuleScope process.

    Attributes:
        mongo_uri: Connection string of the operational database (env
            ``MONGO_URI``). Secret because it may embed credentials.
        mongo_db_name: Operational database name (env ``MONGO_DB_NAME``).
        groq_api_key: Groq API key, not required in fallback mode.
        gemini_api_key: Gemini API key, not required in fallback mode.
        llm_mode: ``live`` or ``fallback`` (env ``LLM_MODE``).
        as_of_date: Dataset end date (env ``AS_OF_DATE``).
        checkpoint_ttl_days: LangGraph checkpoint retention in days (env
            ``CHECKPOINT_TTL_DAYS``).
        mongo_server_selection_timeout_ms: Mongo server selection timeout in
            milliseconds (env ``MONGO_SERVER_SELECTION_TIMEOUT_MS``).
        config_dir: Directory holding ``config/*.yaml`` (env ``CONFIG_DIR``).
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    mongo_uri: SecretStr
    mongo_db_name: str = Field(default="mulescope", min_length=1)
    groq_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    llm_mode: LlmMode = LlmMode.FALLBACK
    as_of_date: date = DEFAULT_AS_OF_DATE
    checkpoint_ttl_days: int = Field(default=7, gt=0)
    mongo_server_selection_timeout_ms: int = Field(default=5000, gt=0)
    config_dir: Path = CONFIG_DIR

    @field_validator("groq_api_key", "gemini_api_key", mode="before")
    @classmethod
    def _empty_key_is_unset(cls, value: object) -> object:
        """Treat an empty ``KEY=`` line in ``.env`` as no key."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def graph_version(self) -> str:
        """Return the graph code version stamped on case runs.

        Returns:
            The :data:`GRAPH_VERSION` constant.
        """
        return GRAPH_VERSION

    @property
    def checkpoint_ttl_seconds(self) -> int:
        """Return the checkpoint retention in seconds.

        This is the value passed to ``MongoDBSaver(ttl=...)``.

        Returns:
            ``checkpoint_ttl_days`` expressed in whole seconds.
        """
        return int(timedelta(days=self.checkpoint_ttl_days).total_seconds())


class ApiSettings(BaseAppSettings):
    """Settings for the API process (``uv run dev``).

    Deliberately has no truth database field. A ``MONGO_TRUTH_URI`` present in
    the environment or a ``.env`` file is ignored and never exposed.

    Attributes:
        api_host: Interface uvicorn binds to (env ``API_HOST``).
        api_port: Port uvicorn listens on (env ``API_PORT``).
    """

    api_host: str = Field(default="127.0.0.1", min_length=1)
    api_port: int = Field(default=8000, gt=0, lt=65536)
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")


class _TruthSettingsMixin(BaseAppSettings):
    """Adds the truth database connection. Used only by datagen and evals.

    Attributes:
        mongo_truth_uri: Truth database connection string (env
            ``MONGO_TRUTH_URI``). Secret because it may embed credentials.
        mongo_truth_db_name: Truth database name (env ``MONGO_TRUTH_DB_NAME``).
    """

    mongo_truth_uri: SecretStr
    mongo_truth_db_name: str = Field(default="mulescope_truth", min_length=1)


class DatagenSettings(_TruthSettingsMixin):
    """Settings for the datagen process (``uv run seed``).

    The only process allowed to bootstrap the truth database.
    """


class EvalsSettings(_TruthSettingsMixin):
    """Settings for the evals process (``uv run evals``).

    Reads the truth database to score runs; never writes to it.
    """
