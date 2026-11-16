"""Baseline ``$jsonSchema`` validators for collections populated from M3 on.

Each baseline enforces only the ``_id`` type for its collection and a required
``date`` ``created_at``. The validators are tightened by the milestone that
implements each entity. Also defines the truth-database ``ground_truth``
baseline. Assembled by ``validators``; not imported elsewhere.

Mutability flags are not applied here: ``updated_at`` / ``schema_version``
become required when each entity's full validator lands.
"""

from collections.abc import Mapping
from types import MappingProxyType

from backend.app.domain.enums import IdPrefix
from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.collection_names import TruthCollection
from backend.app.repositories.mongo.validators_common import (
    JsonSchema,
    document_validator,
    object_id,
    prefixed_string_id,
    string_id,
)


def _baseline(id_schema: JsonSchema) -> JsonSchema:
    """Build a baseline validator: ``_id`` type plus required ``created_at``.

    Args:
        id_schema: Schema for ``_id``.

    Returns:
        A ``{"$jsonSchema": ...}`` validator document.
    """
    return document_validator(id_schema, mutable=False)


BASELINE_VALIDATORS: Mapping[str, JsonSchema] = MappingProxyType(
    {
        Col.USERS: _baseline(prefixed_string_id(IdPrefix.USER)),
        Col.CASES: _baseline(prefixed_string_id(IdPrefix.CASE)),
        Col.CASE_RUNS: _baseline(prefixed_string_id(IdPrefix.CASE_RUN)),
        Col.EVIDENCE: _baseline(prefixed_string_id(IdPrefix.EVIDENCE)),
        Col.REPORTS: _baseline(prefixed_string_id(IdPrefix.REPORT)),
        Col.ACTIONS: _baseline(prefixed_string_id(IdPrefix.ACTION)),
        Col.DECISIONS: _baseline(prefixed_string_id(IdPrefix.DECISION)),
        Col.NODE_EXECUTIONS: _baseline(object_id()),
        Col.AUDIT_LOGS: _baseline(object_id()),
        Col.LLM_CACHE: _baseline(string_id()),
        Col.EVAL_RUNS: _baseline(string_id()),
        Col.EVAL_RESULTS: _baseline(string_id()),
        Col.COUNTERS: _baseline(string_id()),
    }
)
"""Baseline operational validators keyed by collection name."""

TRUTH_BASELINE_VALIDATORS: Mapping[str, JsonSchema] = MappingProxyType(
    {TruthCollection.GROUND_TRUTH: _baseline(string_id())}
)
"""Baseline truth-database validators keyed by collection name."""
