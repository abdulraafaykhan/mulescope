"""Smoke tests for the shared MongoDB fixtures in ``tests/conftest.py``.

They prove the suite reaches a real MongoDB through the configured settings,
that each module gets short, distinct test databases that are never the
production ones, and that ``test_api_settings`` points at the test database.
"""

from __future__ import annotations

from typing import Any

import pytest
from pymongo.asynchronous.database import AsyncDatabase

from backend.app.core.settings import ApiSettings
from tests.conftest import (
    MAX_DB_NAME_BYTES,
    PRODUCTION_DB_NAMES,
    TEST_DB_PREFIX,
    TEST_TRUTH_DB_PREFIX,
    TestDbNames,
    assert_safe_test_db_name,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


async def test_both_test_databases_answer_ping(
    test_db: AsyncDatabase[Any], truth_test_db: AsyncDatabase[Any]
) -> None:
    for db in (test_db, truth_test_db):
        reply = await db.command("ping")
        assert reply["ok"] == 1


async def test_test_databases_are_writable(
    test_db: AsyncDatabase[Any], truth_test_db: AsyncDatabase[Any]
) -> None:
    # Writing materialises both databases, so module teardown really drops them.
    for db in (test_db, truth_test_db):
        await db["smoke"].insert_one({"_id": "smoke"})
        assert await db["smoke"].count_documents({}) == 1


async def test_names_are_short_distinct_and_not_production(
    test_db: AsyncDatabase[Any],
    truth_test_db: AsyncDatabase[Any],
    test_db_names: TestDbNames,
    production_db_names: frozenset[str],
) -> None:
    assert test_db.name == test_db_names.operational
    assert truth_test_db.name == test_db_names.truth
    assert test_db.name != truth_test_db.name
    assert test_db.name.startswith(TEST_DB_PREFIX)
    assert truth_test_db.name.startswith(TEST_TRUTH_DB_PREFIX)
    assert production_db_names >= PRODUCTION_DB_NAMES
    for name in (test_db.name, truth_test_db.name):
        assert len(name.encode("utf-8")) <= MAX_DB_NAME_BYTES
        assert name not in production_db_names


async def test_api_settings_target_the_test_database(
    test_api_settings: ApiSettings, test_db_names: TestDbNames
) -> None:
    assert test_api_settings.mongo_db_name == test_db_names.operational
    assert test_api_settings.mongo_db_name not in PRODUCTION_DB_NAMES


@pytest.mark.parametrize("name", sorted(PRODUCTION_DB_NAMES))
async def test_guard_rejects_production_names(name: str) -> None:
    with pytest.raises(AssertionError):
        assert_safe_test_db_name(name, PRODUCTION_DB_NAMES)
