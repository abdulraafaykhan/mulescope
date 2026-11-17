"""Public registry of ``$jsonSchema`` validators per collection.

Assembles the full M1 validators (``validators_m1``) and the baseline
validators (``validators_baseline``) into one read-only mapping per database.
``bootstrap.ensure_collections`` reads ``OPERATIONAL_VALIDATORS`` and
``bootstrap.ensure_truth_collections`` reads ``TRUTH_VALIDATORS``.

The checkpointer collections (``checkpoints``, ``checkpoint_writes``) are not
listed: ``MongoDBSaver`` owns them and our bootstrap never touches them.
"""

from collections.abc import Mapping
from types import MappingProxyType

from backend.app.repositories.mongo.collection_names import (
    OperationalCollection,
    TruthCollection,
)
from backend.app.repositories.mongo.validators_baseline import (
    BASELINE_VALIDATORS,
    TRUTH_BASELINE_VALIDATORS,
)
from backend.app.repositories.mongo.validators_common import JsonSchema
from backend.app.repositories.mongo.validators_m1 import M1_VALIDATORS


def _assemble(
    expected: frozenset[str], *parts: Mapping[str, JsonSchema]
) -> Mapping[str, JsonSchema]:
    """Merge validator mappings and check they cover exactly ``expected``.

    Args:
        expected: Collection names that must each have exactly one validator.
        *parts: Validator mappings to merge.

    Returns:
        A read-only mapping of collection name to validator document.

    Raises:
        ValueError: If a collection is defined twice, missing or unexpected.
    """
    merged: dict[str, JsonSchema] = {}
    for part in parts:
        duplicates = merged.keys() & part.keys()
        if duplicates:
            raise ValueError(f"Validator defined more than once: {sorted(duplicates)}")
        merged.update(part)
    if merged.keys() != expected:
        missing = sorted(expected - merged.keys())
        extra = sorted(merged.keys() - expected)
        raise ValueError(f"Validator coverage mismatch: missing={missing}, extra={extra}")
    return MappingProxyType(merged)


OPERATIONAL_VALIDATORS: Mapping[str, JsonSchema] = _assemble(
    frozenset(OperationalCollection), M1_VALIDATORS, BASELINE_VALIDATORS
)
"""Validator per operational ``mulescope`` collection."""

TRUTH_VALIDATORS: Mapping[str, JsonSchema] = _assemble(
    frozenset(TruthCollection), TRUTH_BASELINE_VALIDATORS
)
"""Validator per truth ``mulescope_truth`` collection (datagen only)."""
