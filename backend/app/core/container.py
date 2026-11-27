"""Composition root for the API process.

Built once by the FastAPI lifespan in ``main.py``. It owns the two Mongo
clients (async for the app, sync for the LangGraph checkpointer), runs the
collection bootstrap, compiles the graph and wires repositories and services.
Routers reach these objects only through ``api/deps.py``.

The container is built from ``ApiSettings`` and never holds a truth-database
handle.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pymongo import AsyncMongoClient, MongoClient
from pymongo.asynchronous.database import AsyncDatabase

from backend.app.core.config_files import LlmConfig, load_llm_config
from backend.app.core.logging import get_logger
from backend.app.core.settings import ApiSettings
from backend.app.graph.checkpoint import build_checkpointer
from backend.app.repositories.mongo.bootstrap import ensure_collections
from backend.app.repositories.mongo.health_probe import MongoHealthProbe
from backend.app.services.system_service import SystemService, SystemSettingsView

_logger = get_logger(__name__)


class Container:
    """Holds every long-lived object of the API process.

    Args:
        settings: API settings (no truth connection).
        llm_config: Parsed ``config/llm.yaml``.
    """

    def __init__(self, settings: ApiSettings, llm_config: LlmConfig | None = None) -> None:
        self.settings = settings
        self.llm_config = llm_config or load_llm_config(settings.config_dir)
        self._client: AsyncMongoClient[Any] | None = None
        self._sync_client: MongoClient[Any] | None = None
        self._db: AsyncDatabase[Any] | None = None
        self.checkpointer: Any = None
        self.system_service: SystemService | None = None
        self.extras: dict[str, Any] = {}

    @property
    def db(self) -> AsyncDatabase[Any]:
        """Operational database handle. Raises before ``startup``."""
        if self._db is None:
            raise RuntimeError("Container.startup() has not run")
        return self._db

    def _settings_view(self) -> SystemSettingsView:
        s = self.settings
        return SystemSettingsView(
            llm_mode=s.llm_mode,
            graph_version=s.graph_version,
            config_versions={"llm": self.llm_config.version},
            groq_key_configured=s.groq_api_key is not None,
            gemini_key_configured=s.gemini_api_key is not None,
        )

    async def startup(self) -> None:
        """Connect, bootstrap collections, build the checkpointer and services."""
        s = self.settings
        uri = s.mongo_uri.get_secret_value()
        timeout = s.mongo_server_selection_timeout_ms
        self._client = AsyncMongoClient(uri, serverSelectionTimeoutMS=timeout, tz_aware=True)
        self._db = self._client[s.mongo_db_name]
        await ensure_collections(
            self._db, self.llm_config.cache_ttl_seconds, self.llm_config.call_log_ttl_seconds
        )

        # MongoDBSaver creates its indexes in __init__ (blocking I/O), so keep it off the loop.
        def _build_saver() -> tuple[MongoClient[Any], Any]:
            sync_client: MongoClient[Any] = MongoClient(uri, serverSelectionTimeoutMS=timeout)
            return sync_client, build_checkpointer(
                sync_client, s.mongo_db_name, s.checkpoint_ttl_seconds
            )

        self._sync_client, self.checkpointer = await asyncio.to_thread(_build_saver)
        self.system_service = SystemService(MongoHealthProbe(self._db), self._settings_view())
        await self._wire_application()
        _logger.info("container started", extra={"db": s.mongo_db_name})

    async def _wire_application(self) -> None:
        """Build repositories, services and the graph. Filled in by later phases."""
        from backend.app.core.wiring import wire  # local import keeps startup order explicit

        await wire(self)

    async def shutdown(self) -> None:
        """Close the LLM HTTP clients and both Mongo clients."""
        app = self.extras.get("app")
        if app is not None:
            await app.deps.agents.aclose()
        if self._client is not None:
            await self._client.close()
        if self._sync_client is not None:
            await asyncio.to_thread(self._sync_client.close)
        _logger.info("container stopped")
