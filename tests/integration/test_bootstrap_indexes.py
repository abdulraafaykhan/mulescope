"""Property 3 (bootstrap part): index and validator completeness.

After one ``ensure_collections`` run on a fresh database:

* every ``IndexSpec`` in the operational plan exists under its name with exactly
  the planned keys (order and direction), ``unique`` flag, TTL and
  ``partialFilterExpression``; the ``llm_cache`` ``created_at`` TTL equals the
  value configured in ``config/llm.yaml``;
* every operational collection rejects a document whose ``_id`` has the wrong
  type or prefix;
* ``checkpoints`` / ``checkpoint_writes`` do not exist (``MongoDBSaver`` owns
  them, our bootstrap never creates them).

The truth side checks that ``ensure_truth_collections`` creates every
``TRUTH_INDEX_PLAN`` index on ``ground_truth``.

How ``_id`` rejection is attributed to ``_id``
----------------------------------------------
Probe documents are minimal: ``{"_id": <id>, "created_at": <now UTC>}``. For
baseline collections that is a complete valid document, but the full M1
validators also require collection-specific fields, so a minimal document is
rejected there whatever its ``_id``. To prove the rejection is caused by
``_id`` the test reads MongoDB's ``errInfo.details`` (DocumentValidationFailure,
code 121) and asserts ``_id`` is listed under ``propertiesNotSatisfied``. As a
control, the same minimal document with a correct ``_id`` is either accepted
(baseline collections) or rejected without ``_id`` among the failing
properties (M1 collections).

Expected ``_id`` kinds are written out below from the design's collection plan,
not derived from the validators under test.

The property sets (index specs, collections, wrong-id variants) are finite, so
they are checked exhaustively with ``pytest.mark.parametrize``.

**Validates: Requirements 6.1, 6.2, 6.3, 6.5**
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Mapping
from enum import StrEnum
from typing import Any, Final

import pytest
import pytest_asyncio
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import WriteError

from backend.app.core.clock import SystemClock
from backend.app.core.config_files import load_llm_config
from backend.app.core.settings import CONFIG_DIR
from backend.app.domain.enums import IdPrefix
from backend.app.repositories.mongo.bootstrap import ensure_collections, ensure_truth_collections
from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.index_plan import (
    TRUTH_INDEX_PLAN,
    IndexSpec,
    operational_index_plan,
)
from backend.app.repositories.mongo.validators_m1 import M1_VALIDATORS

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]

LLM_CACHE_TTL_SECONDS: Final[int] = load_llm_config(CONFIG_DIR).cache_ttl_seconds
LLM_CALL_TTL_SECONDS: Final[int] = load_llm_config(CONFIG_DIR).call_log_ttl_seconds
OPERATIONAL_PLAN: Final[tuple[IndexSpec, ...]] = operational_index_plan(
    LLM_CACHE_TTL_SECONDS, LLM_CALL_TTL_SECONDS
)

DOCUMENT_VALIDATION_FAILURE: Final[int] = 121
"""MongoDB error code for a ``$jsonSchema`` rejection."""

CHECKPOINTER_COLLECTIONS: Final[tuple[str, ...]] = ("checkpoints", "checkpoint_writes")
VALID_ID_SUFFIX: Final[str] = "000001"


class IdKind(StrEnum):
    """Expected ``_id`` shape of a collection (design collection plan)."""

    PREFIXED = "prefixed"
    OBJECT_ID = "object_id"
    STRING = "string"


EXPECTED_PREFIX: Final[Mapping[str, IdPrefix]] = {
    Col.CUSTOMERS: IdPrefix.CUSTOMER,
    Col.ACCOUNTS: IdPrefix.ACCOUNT,
    Col.COUNTERPARTIES: IdPrefix.COUNTERPARTY,
    Col.COMPLAINTS: IdPrefix.COMPLAINT,
    Col.USERS: IdPrefix.USER,
    Col.ALERTS: IdPrefix.ALERT,
    Col.CASES: IdPrefix.CASE,
    Col.CASE_RUNS: IdPrefix.CASE_RUN,
    Col.EVIDENCE: IdPrefix.EVIDENCE,
    Col.REPORTS: IdPrefix.REPORT,
    Col.ACTIONS: IdPrefix.ACTION,
    Col.DECISIONS: IdPrefix.DECISION,
}
OBJECT_ID_COLLECTIONS: Final[frozenset[str]] = frozenset(
    {Col.TRANSACTIONS, Col.AUDIT_LOGS, Col.NODE_EXECUTIONS, Col.LLM_CALLS}
)
STRING_ID_COLLECTIONS: Final[frozenset[str]] = frozenset(
    {Col.LLM_CACHE, Col.EVAL_RUNS, Col.EVAL_RESULTS, Col.DATASET_META}
)


def _id_kind(collection: str) -> IdKind:
    """Return the expected ``_id`` kind of ``collection``."""
    if collection in EXPECTED_PREFIX:
        return IdKind.PREFIXED
    if collection in OBJECT_ID_COLLECTIONS:
        return IdKind.OBJECT_ID
    if collection in STRING_ID_COLLECTIONS:
        return IdKind.STRING
    raise AssertionError(f"collection {collection!r} missing from the expected _id table")


def _other_prefix(prefix: IdPrefix) -> IdPrefix:
    """Return a different entity's prefix, used as a wrong-prefix probe."""
    members = list(IdPrefix)
    return members[(members.index(prefix) + 1) % len(members)]


def _valid_id(collection: str) -> Any:
    """Return an ``_id`` of the right shape for ``collection``."""
    kind = _id_kind(collection)
    if kind is IdKind.PREFIXED:
        return f"{EXPECTED_PREFIX[collection].value}{VALID_ID_SUFFIX}"
    if kind is IdKind.OBJECT_ID:
        return ObjectId()
    return f"{collection}-{VALID_ID_SUFFIX}"


def _wrong_ids() -> Iterator[Any]:
    """Yield one ``pytest.param(collection, wrong_id)`` per wrong-id variant."""
    for collection in sorted(Col):
        kind = _id_kind(collection)
        if kind is IdKind.PREFIXED:
            wrong = _other_prefix(EXPECTED_PREFIX[collection])
            yield pytest.param(collection, ObjectId(), id=f"{collection}-objectid")
            yield pytest.param(
                collection, f"{wrong.value}{VALID_ID_SUFFIX}", id=f"{collection}-wrong-prefix"
            )
        elif kind is IdKind.OBJECT_ID:
            yield pytest.param(
                collection, f"{collection}-{VALID_ID_SUFFIX}", id=f"{collection}-string"
            )
        else:
            yield pytest.param(collection, ObjectId(), id=f"{collection}-objectid")


def _failing_properties(exc: WriteError) -> set[str]:
    """Return property names listed as failing in a validation error's ``errInfo``."""
    details = (exc.details or {}).get("errInfo", {}).get("details", {})
    names: set[str] = set()
    for rule in details.get("schemaRulesNotSatisfied", []):
        if rule.get("operatorName") == "properties":
            names.update(p["propertyName"] for p in rule.get("propertiesNotSatisfied", []))
    return names


def _key_pairs(info: Mapping[str, Any]) -> list[tuple[str, int]]:
    """Normalise ``index_information()`` keys to ``(field, int direction)`` pairs."""
    return [(field, int(direction)) for field, direction in info["key"]]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def bootstrapped_db(test_db: AsyncDatabase[Any]) -> AsyncIterator[AsyncDatabase[Any]]:
    """Run ``ensure_collections`` once on the module test database."""
    await ensure_collections(test_db, LLM_CACHE_TTL_SECONDS, LLM_CALL_TTL_SECONDS)
    yield test_db


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def index_info(bootstrapped_db: AsyncDatabase[Any]) -> dict[str, dict[str, Any]]:
    """Return ``index_information()`` for every collection after bootstrap."""
    names = await bootstrapped_db.list_collection_names()
    return {name: await bootstrapped_db[name].index_information() for name in names}


def _assert_index_matches(spec: IndexSpec, indexes: Mapping[str, Any]) -> None:
    """Assert ``spec`` exists in ``indexes`` with exactly its planned options."""
    assert spec.name in indexes, f"index {spec.name} missing on {spec.collection}"
    info = indexes[spec.name]
    assert _key_pairs(info) == [(f, int(d)) for f, d in spec.keys]
    assert bool(info.get("unique", False)) is spec.unique
    if spec.ttl_seconds is None:
        assert "expireAfterSeconds" not in info
    else:
        assert int(info["expireAfterSeconds"]) == spec.ttl_seconds
    if spec.partial_filter is None:
        assert "partialFilterExpression" not in info
    else:
        assert dict(info["partialFilterExpression"]) == dict(spec.partial_filter)


@pytest.mark.parametrize("spec", OPERATIONAL_PLAN, ids=lambda s: s.name)
async def test_planned_index_exists(spec: IndexSpec, index_info: dict[str, dict[str, Any]]) -> None:
    assert spec.collection in index_info, f"collection {spec.collection} missing"
    _assert_index_matches(spec, index_info[spec.collection])


async def test_ttls_match_config(index_info: dict[str, dict[str, Any]]) -> None:
    ttl_specs = [s for s in OPERATIONAL_PLAN if s.ttl_seconds is not None]
    assert [(s.collection, s.keys[0][0]) for s in ttl_specs] == [
        (Col.LLM_CACHE, "created_at"),
        (Col.LLM_CALLS, "created_at"),
    ]
    expected = {Col.LLM_CACHE: LLM_CACHE_TTL_SECONDS, Col.LLM_CALLS: LLM_CALL_TTL_SECONDS}
    for spec in ttl_specs:
        info = index_info[spec.collection][spec.name]
        assert int(info["expireAfterSeconds"]) == expected[spec.collection]


async def test_expected_id_table_covers_every_collection() -> None:
    for collection in Col:
        _id_kind(collection)  # raises if a collection is unaccounted for


@pytest.mark.parametrize(("collection", "bad_id"), list(_wrong_ids()))
async def test_wrong_id_is_rejected(
    bootstrapped_db: AsyncDatabase[Any], collection: str, bad_id: Any
) -> None:
    doc = {"_id": bad_id, "created_at": SystemClock().now()}
    with pytest.raises(WriteError) as caught:
        await bootstrapped_db[collection].insert_one(doc)
    assert caught.value.code == DOCUMENT_VALIDATION_FAILURE
    assert "_id" in _failing_properties(caught.value)


@pytest.mark.parametrize("collection", sorted(Col))
async def test_correct_id_is_not_the_failure(
    bootstrapped_db: AsyncDatabase[Any], collection: str
) -> None:
    """Control: with a correct ``_id`` the minimal document never fails on ``_id``."""
    doc = {"_id": _valid_id(collection), "created_at": SystemClock().now()}
    if collection not in M1_VALIDATORS:
        await bootstrapped_db[collection].insert_one(doc)  # baseline: fully valid
        return
    with pytest.raises(WriteError) as caught:
        await bootstrapped_db[collection].insert_one(doc)
    assert caught.value.code == DOCUMENT_VALIDATION_FAILURE
    assert "_id" not in _failing_properties(caught.value)


async def test_checkpointer_collections_untouched(index_info: dict[str, dict[str, Any]]) -> None:
    for name in CHECKPOINTER_COLLECTIONS:
        assert name not in index_info, f"{name} created by ensure_collections"


async def test_truth_indexes_exist(truth_test_db: AsyncDatabase[Any]) -> None:
    await ensure_truth_collections(truth_test_db)
    for spec in TRUTH_INDEX_PLAN:
        indexes = await truth_test_db[spec.collection].index_information()
        _assert_index_matches(spec, indexes)
