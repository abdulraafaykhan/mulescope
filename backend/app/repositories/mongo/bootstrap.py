"""Idempotent creation of MongoDB collections, validators and indexes.

``ensure_collections`` is called once at API startup by ``core.container``.
``ensure_truth_collections`` is called only by ``datagen`` (``uv run seed``).

For every collection in the plan:

1. A missing collection is created with its ``$jsonSchema`` validator.
2. An existing collection gets its validator refreshed with ``collMod``.
3. Every named index from the index plan is created. ``create_index`` with an
   identical name, keys and options is a no-op, so re-runs are safe.

Validation level and action are left at the MongoDB defaults (``strict`` and
``error``): every insert and update is validated, and invalid writes are
rejected rather than logged.

The LangGraph checkpointer collections (``checkpoints``, ``checkpoint_writes``)
are never created, modified or indexed here: ``MongoDBSaver`` owns them. They
are absent from both the validator registry and the index plan.

Connection failures become :class:`DependencyUnavailable` with a message that
never includes the connection string. An existing index with the same name but
different options also becomes :class:`DependencyUnavailable`; it is never
dropped automatically. Any other ``OperationFailure`` propagates unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import (
    AutoReconnect,
    CollectionInvalid,
    ConnectionFailure,
    NetworkTimeout,
    OperationFailure,
    ServerSelectionTimeoutError,
)

from backend.app.core.errors import DependencyUnavailable
from backend.app.core.logging import get_logger
from backend.app.repositories.mongo.index_plan import (
    TRUTH_INDEX_PLAN,
    IndexSpec,
    operational_index_plan,
)
from backend.app.repositories.mongo.validators import (
    OPERATIONAL_VALIDATORS,
    TRUTH_VALIDATORS,
)
from backend.app.repositories.mongo.validators_common import JsonSchema

__all__ = ["ensure_collections", "ensure_truth_collections"]

_logger = get_logger(__name__)

_CONNECTION_ERRORS: Final[tuple[type[Exception], ...]] = (
    ServerSelectionTimeoutError,
    NetworkTimeout,
    AutoReconnect,
    ConnectionFailure,
)
"""PyMongo errors that mean the server could not be reached."""

_INDEX_CONFLICT_CODES: Final[frozenset[int]] = frozenset({85, 86})
"""``IndexOptionsConflict`` (85) and ``IndexKeySpecsConflict`` (86)."""


async def ensure_collections(
    db: AsyncDatabase[Any], llm_cache_ttl_seconds: int, llm_call_ttl_seconds: int
) -> None:
    """Create or refresh every operational collection, validator and index.

    Args:
        db: Handle to the operational ``mulescope`` database.
        llm_cache_ttl_seconds: ``expireAfterSeconds`` for the ``llm_cache``
            ``created_at`` TTL index, from ``LlmConfig.cache_ttl_seconds``.
        llm_call_ttl_seconds: ``expireAfterSeconds`` for the ``llm_calls``
            ``created_at`` TTL index, from ``LlmConfig.call_log_ttl_seconds``.

    Raises:
        DependencyUnavailable: If MongoDB is unreachable, or an existing index
            has the same name as a planned one but different options.
        ValueError: If either TTL is not positive.
    """
    plan = operational_index_plan(llm_cache_ttl_seconds, llm_call_ttl_seconds)
    await _ensure(db, OPERATIONAL_VALIDATORS, plan, database_role="operational")


async def ensure_truth_collections(truth_db: AsyncDatabase[Any]) -> None:
    """Create or refresh the truth collections, validators and indexes.

    Only ``datagen`` may call this. The API process has no truth connection
    and must never reference this function.

    Args:
        truth_db: Handle to the ``mulescope_truth`` database.

    Raises:
        DependencyUnavailable: If MongoDB is unreachable, or an existing index
            has the same name as a planned one but different options.
    """
    await _ensure(truth_db, TRUTH_VALIDATORS, TRUTH_INDEX_PLAN, database_role="truth")


async def _ensure(
    db: AsyncDatabase[Any],
    validators: Mapping[str, JsonSchema],
    plan: Iterable[IndexSpec],
    *,
    database_role: str,
) -> None:
    """Apply validators and indexes for one database.

    Args:
        db: Target database handle.
        validators: Validator document per collection name.
        plan: Index specs for the collections in ``validators``.
        database_role: ``operational`` or ``truth``, used only in logs and
            error messages (never the connection string).

    Raises:
        DependencyUnavailable: On connection failure or index option conflict.
        ValueError: If the plan references a collection with no validator.
    """
    specs_by_collection: dict[str, list[IndexSpec]] = {name: [] for name in validators}
    for spec in plan:
        if spec.collection not in specs_by_collection:
            raise ValueError(f"index {spec.name!r} targets unknown collection {spec.collection!r}")
        specs_by_collection[spec.collection].append(spec)

    try:
        existing = set(await db.list_collection_names())
        for name, validator in validators.items():
            created = await _ensure_validator(db, name, validator, exists=name in existing)
            index_names = [await _ensure_index(db, spec) for spec in specs_by_collection[name]]
            _logger.info(
                "collection ensured",
                extra={
                    "database_role": database_role,
                    "collection": name,
                    "collection_created": created,
                    "indexes": index_names,
                },
            )
    except _CONNECTION_ERRORS as exc:
        raise DependencyUnavailable(
            f"MongoDB {database_role} database is unreachable during bootstrap",
            detail={"database_role": database_role, "error_type": type(exc).__name__},
        ) from exc


async def _ensure_validator(
    db: AsyncDatabase[Any], name: str, validator: JsonSchema, *, exists: bool
) -> bool:
    """Create the collection with its validator, or refresh it with ``collMod``.

    Args:
        db: Target database handle.
        name: Collection name.
        validator: ``{"$jsonSchema": ...}`` validator document.
        exists: Whether the collection was present before bootstrapping.

    Returns:
        ``True`` if the collection was created by this call.
    """
    if not exists:
        try:
            await db.create_collection(name, validator=validator)
            return True
        except CollectionInvalid:
            pass  # Created concurrently by another process; refresh below.
    await db.command("collMod", name, validator=validator)
    return False


async def _ensure_index(db: AsyncDatabase[Any], spec: IndexSpec) -> str:
    """Create one named index idempotently.

    Args:
        db: Target database handle.
        spec: The index to create.

    Returns:
        The index name.

    Raises:
        DependencyUnavailable: If an index with the same name or keys exists
            with different options. The existing index is left in place.
    """
    options: dict[str, Any] = {"name": spec.name, "unique": spec.unique}
    if spec.ttl_seconds is not None:
        options["expireAfterSeconds"] = spec.ttl_seconds
    if spec.partial_filter is not None:
        options["partialFilterExpression"] = dict(spec.partial_filter)
    try:
        return await db[spec.collection].create_index(list(spec.keys), **options)
    except OperationFailure as exc:
        if exc.code in _INDEX_CONFLICT_CODES:
            raise DependencyUnavailable(
                f"Index {spec.name!r} on collection {spec.collection!r} already exists "
                "with different options; drop or rename it manually",
                detail={"collection": spec.collection, "index": spec.name, "code": exc.code},
            ) from exc
        raise
