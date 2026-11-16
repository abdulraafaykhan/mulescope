"""Shared pytest fixtures for MuleScope tests, backed by a real MongoDB.

Integration tests run against a real MongoDB (build prompt section 10.4), never
mongomock. The connection comes from the same settings classes the app uses:

* operational URI: ``ApiSettings().mongo_uri``;
* truth URI: ``DatagenSettings().mongo_truth_uri``.

Both read ``.env`` files and real environment variables, and real environment
variables win, which is how CI points the suite at its ``mongo:7`` service
container. If ``MONGO_URI`` is unset everywhere the suite falls back to
:data:`DEFAULT_LOCAL_MONGO_URI`; if ``MONGO_TRUTH_URI`` is unset it reuses the
operational URI.

Every test module gets its own short, unique databases (Atlas caps database
names at 38 bytes) which are dropped when the module finishes, pass or fail.

Rules kept by this module:

* Importing it, or running ``pytest --co``, never opens a connection: settings
  and clients are built inside fixtures only.
* Nothing that connects is ``autouse``. Unit tests never request these
  fixtures, so they run with no database.
* When MongoDB is unreachable the requesting test fails with a clear message.
  Nothing is skipped silently. Messages never include URIs, hosts or
  credentials.

Async fixtures are module-scoped and run on the module event loop
(``loop_scope="module"``). Tests that use them must run on the same loop, so
integration modules set
``pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Final

import pytest
import pytest_asyncio
from pydantic import SecretStr, ValidationError
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from backend.app.core.settings import ApiSettings, DatagenSettings

DEFAULT_LOCAL_MONGO_URI: Final[str] = "mongodb://localhost:27017"
"""Used only when ``MONGO_URI`` is set nowhere (no env var, no ``.env``)."""

TEST_DB_PREFIX: Final[str] = "mst_"
"""Prefix of per-module operational test databases."""

TEST_TRUTH_DB_PREFIX: Final[str] = "mstt_"
"""Prefix of per-module truth test databases."""

TEST_DB_HEX_LENGTH: Final[int] = 12
"""Number of random hex characters appended to each test database prefix."""

MAX_DB_NAME_BYTES: Final[int] = 38
"""Atlas limit on database name length, in bytes."""

PRODUCTION_DB_NAMES: Final[frozenset[str]] = frozenset({"mulescope", "mulescope_truth"})
"""Database names the test suite must never touch."""

_UNREACHABLE_MESSAGE: Final[str] = (
    "MongoDB ({role}) is unreachable for the integration tests ({error_type}). "
    "Check MONGO_URI / MONGO_TRUTH_URI and, for Atlas, that this machine's IP is "
    "allowed under Network Access. For a local server run `docker compose up -d` "
    "from mulescope/."
)


@dataclass(frozen=True, slots=True)
class TestDbNames:
    """Per-module test database names.

    Attributes:
        operational: Name of the operational test database.
        truth: Name of the truth test database.
    """

    __test__ = False  # not a test class, despite the name

    operational: str
    truth: str


def _new_db_name(prefix: str) -> str:
    """Return a short unique database name.

    Args:
        prefix: Name prefix, for example :data:`TEST_DB_PREFIX`.

    Returns:
        ``prefix`` followed by :data:`TEST_DB_HEX_LENGTH` random hex characters.
    """
    return f"{prefix}{uuid.uuid4().hex[:TEST_DB_HEX_LENGTH]}"


def assert_safe_test_db_name(name: str, production_names: frozenset[str]) -> None:
    """Guard against ever pointing a test at a production database.

    Args:
        name: Candidate test database name.
        production_names: Names that must never be used.

    Raises:
        AssertionError: If ``name`` is a production name, has no test prefix,
            or exceeds :data:`MAX_DB_NAME_BYTES`.
    """
    assert name not in production_names, "test database name equals a production name"
    assert name.startswith((TEST_DB_PREFIX, TEST_TRUTH_DB_PREFIX)), "missing test prefix"
    assert len(name.encode("utf-8")) <= MAX_DB_NAME_BYTES, "test database name too long"


def _load_api_settings() -> ApiSettings:
    """Load ``ApiSettings``, falling back to a local URI when none is configured."""
    try:
        return ApiSettings()
    except ValidationError:
        # Only MONGO_URI is required; anything else invalid fails again here.
        return ApiSettings(mongo_uri=SecretStr(DEFAULT_LOCAL_MONGO_URI))


def _load_datagen_settings(operational_uri: SecretStr) -> DatagenSettings:
    """Load ``DatagenSettings``, filling missing URIs from the operational one."""
    try:
        return DatagenSettings()
    except ValidationError:
        try:
            return DatagenSettings(mongo_truth_uri=operational_uri)
        except ValidationError:
            return DatagenSettings(mongo_uri=operational_uri, mongo_truth_uri=operational_uri)


async def _connect(uri: SecretStr, timeout_ms: int, role: str) -> AsyncMongoClient[Any]:
    """Create an async client and prove it can reach the server.

    Args:
        uri: Connection string (kept secret; never logged).
        timeout_ms: Server selection timeout in milliseconds.
        role: ``operational`` or ``truth``, used in the failure message.

    Returns:
        A connected ``AsyncMongoClient``.
    """
    client: AsyncMongoClient[Any] = AsyncMongoClient(
        uri.get_secret_value(), serverSelectionTimeoutMS=timeout_ms
    )
    error_type: str | None = None
    try:
        await client.admin.command("ping")
    except PyMongoError as exc:
        error_type = type(exc).__name__
    if error_type is not None:
        await client.close()
        # Raised outside the except block so no chained traceback (which can
        # name hosts) is attached; pytrace=False keeps the report to the message.
        pytest.fail(_UNREACHABLE_MESSAGE.format(role=role, error_type=error_type), pytrace=False)
    return client


# --- settings and names: no I/O -------------------------------------------------


@pytest.fixture(scope="module")
def base_api_settings() -> ApiSettings:
    """Return ``ApiSettings`` as configured for this machine. Opens no connection."""
    return _load_api_settings()


@pytest.fixture(scope="module")
def base_datagen_settings(base_api_settings: ApiSettings) -> DatagenSettings:
    """Return ``DatagenSettings`` as configured for this machine. Opens no connection."""
    return _load_datagen_settings(base_api_settings.mongo_uri)


@pytest.fixture(scope="module")
def production_db_names(
    base_api_settings: ApiSettings, base_datagen_settings: DatagenSettings
) -> frozenset[str]:
    """Return every database name the tests must never use."""
    return PRODUCTION_DB_NAMES | {
        base_api_settings.mongo_db_name,
        base_datagen_settings.mongo_truth_db_name,
    }


@pytest.fixture(scope="module")
def test_db_names(production_db_names: frozenset[str]) -> TestDbNames:
    """Return fresh, guarded test database names for this module."""
    names = TestDbNames(
        operational=_new_db_name(TEST_DB_PREFIX),
        truth=_new_db_name(TEST_TRUTH_DB_PREFIX),
    )
    for name in (names.operational, names.truth):
        assert_safe_test_db_name(name, production_db_names)
    assert names.operational != names.truth
    return names


@pytest.fixture(scope="module")
def test_api_settings(base_api_settings: ApiSettings, test_db_names: TestDbNames) -> ApiSettings:
    """Return ``ApiSettings`` pointed at this module's operational test database."""
    return base_api_settings.model_copy(update={"mongo_db_name": test_db_names.operational})


@pytest.fixture(scope="module")
def test_datagen_settings(
    base_datagen_settings: DatagenSettings, test_db_names: TestDbNames
) -> DatagenSettings:
    """Return ``DatagenSettings`` pointed at this module's test databases."""
    return base_datagen_settings.model_copy(
        update={
            "mongo_db_name": test_db_names.operational,
            "mongo_truth_db_name": test_db_names.truth,
        }
    )


# --- connections: integration tests only ----------------------------------------


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def mongo_client(base_api_settings: ApiSettings) -> AsyncIterator[AsyncMongoClient[Any]]:
    """Yield one operational ``AsyncMongoClient`` for the module, closed afterwards."""
    client = await _connect(
        base_api_settings.mongo_uri,
        base_api_settings.mongo_server_selection_timeout_ms,
        role="operational",
    )
    try:
        yield client
    finally:
        await client.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def truth_mongo_client(
    base_api_settings: ApiSettings,
    base_datagen_settings: DatagenSettings,
    mongo_client: AsyncMongoClient[Any],
) -> AsyncIterator[AsyncMongoClient[Any]]:
    """Yield the truth client: the operational client when both URIs match."""
    truth_uri = base_datagen_settings.mongo_truth_uri
    if truth_uri.get_secret_value() == base_api_settings.mongo_uri.get_secret_value():
        yield mongo_client
        return
    client = await _connect(
        truth_uri, base_datagen_settings.mongo_server_selection_timeout_ms, role="truth"
    )
    try:
        yield client
    finally:
        await client.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def test_db(
    mongo_client: AsyncMongoClient[Any],
    test_db_names: TestDbNames,
    production_db_names: frozenset[str],
) -> AsyncIterator[AsyncDatabase[Any]]:
    """Yield this module's operational test database; drop it afterwards."""
    assert_safe_test_db_name(test_db_names.operational, production_db_names)
    try:
        yield mongo_client[test_db_names.operational]
    finally:
        await mongo_client.drop_database(test_db_names.operational)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def truth_test_db(
    truth_mongo_client: AsyncMongoClient[Any],
    test_db_names: TestDbNames,
    production_db_names: frozenset[str],
) -> AsyncIterator[AsyncDatabase[Any]]:
    """Yield this module's truth test database; drop it afterwards."""
    assert_safe_test_db_name(test_db_names.truth, production_db_names)
    try:
        yield truth_mongo_client[test_db_names.truth]
    finally:
        await truth_mongo_client.drop_database(test_db_names.truth)
