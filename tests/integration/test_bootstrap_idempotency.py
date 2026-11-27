"""Property 2: bootstrap idempotency.

Running ``ensure_collections`` 1, 2 or 3 times on a fresh database yields the
same collections and the same ``index_information()`` on every collection,
with no error and no duplicate indexes. A collection that already exists
without a validator gets the planned validator applied.

The run-count set is finite, so the property is checked exhaustively with
``pytest.mark.parametrize`` (Hypothesis is not in the stack).

Each case runs on its own short, guarded sub-database (``mst_`` + hex) on the
module client, dropped in ``finally``. The ``llm_cache`` TTL comes from
``config/llm.yaml`` via ``load_llm_config``, never a literal.

**Validates: Requirements 6.1, 6.8**
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import pytest
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from backend.app.core.config_files import load_llm_config
from backend.app.core.settings import CONFIG_DIR
from backend.app.repositories.mongo.bootstrap import ensure_collections
from backend.app.repositories.mongo.index_plan import operational_index_plan
from backend.app.repositories.mongo.validators import OPERATIONAL_VALIDATORS
from tests.conftest import TEST_DB_HEX_LENGTH, TEST_DB_PREFIX, assert_safe_test_db_name

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]

RUN_COUNTS = (1, 2, 3)
"""Number of consecutive ``ensure_collections`` calls per case."""

DEFAULT_ID_INDEX = "_id_"
"""Name of the index MongoDB creates on ``_id`` for every collection."""

LLM_CACHE_TTL_SECONDS = load_llm_config(CONFIG_DIR).cache_ttl_seconds
LLM_CALL_TTL_SECONDS = load_llm_config(CONFIG_DIR).call_log_ttl_seconds

Snapshot = dict[str, dict[str, Any]]
"""Collection name -> ``index_information()`` of that collection."""

FreshDb = Callable[[], AbstractAsyncContextManager[AsyncDatabase[Any]]]


@pytest.fixture(scope="module")
def fresh_db(mongo_client: AsyncMongoClient[Any], production_db_names: frozenset[str]) -> FreshDb:
    """Return a factory for a fresh, guarded sub-database dropped on exit."""

    @asynccontextmanager
    async def _fresh() -> AsyncIterator[AsyncDatabase[Any]]:
        name = f"{TEST_DB_PREFIX}{uuid.uuid4().hex[:TEST_DB_HEX_LENGTH]}"
        assert_safe_test_db_name(name, production_db_names)
        try:
            yield mongo_client[name]
        finally:
            await mongo_client.drop_database(name)

    return _fresh


async def _snapshot(db: AsyncDatabase[Any]) -> Snapshot:
    """Return the index information of every collection in ``db``."""
    names = sorted(await db.list_collection_names())
    return {name: await db[name].index_information() for name in names}


def _expected_index_names() -> dict[str, set[str]]:
    """Return the index names the plan requires per operational collection."""
    expected: dict[str, set[str]] = {name: {DEFAULT_ID_INDEX} for name in OPERATIONAL_VALIDATORS}
    for spec in operational_index_plan(LLM_CACHE_TTL_SECONDS, LLM_CALL_TTL_SECONDS):
        expected[spec.collection].add(spec.name)
    return expected


@pytest.mark.parametrize("runs", RUN_COUNTS)
async def test_repeated_bootstrap_is_identical(fresh_db: FreshDb, runs: int) -> None:
    expected = _expected_index_names()
    async with fresh_db() as db:
        snapshots: list[Snapshot] = []
        for _ in range(runs):
            await ensure_collections(db, LLM_CACHE_TTL_SECONDS, LLM_CALL_TTL_SECONDS)
            snapshots.append(await _snapshot(db))

    first = snapshots[0]
    # Same collections and indexes as the plan, so every run count is
    # compared against one fixed reference, not only against itself.
    assert set(first) == set(expected)
    for name, info in first.items():
        assert set(info) == expected[name], name
        key_specs = [tuple(map(tuple, index["key"])) for index in info.values()]
        assert len(key_specs) == len(set(key_specs)), f"duplicate index keys on {name}"
    for later in snapshots[1:]:
        assert later == first


async def test_existing_collection_without_validator_gets_it(fresh_db: FreshDb) -> None:
    target = sorted(OPERATIONAL_VALIDATORS)[0]
    async with fresh_db() as db:
        await db.create_collection(target)
        before = await db.list_collections(filter={"name": target})
        before_options = (await before.to_list())[0].get("options", {})
        assert "validator" not in before_options

        await ensure_collections(db, LLM_CACHE_TTL_SECONDS, LLM_CALL_TTL_SECONDS)

        after = await db.list_collections(filter={"name": target})
        after_options = (await after.to_list())[0]["options"]
    assert after_options["validator"] == dict(OPERATIONAL_VALIDATORS[target])
