"""Declarative MongoDB index plan for the operational and truth databases.

Pure data: no database calls. ``bootstrap`` reads these plans and creates the
indexes idempotently; tests read them to assert every named index exists.

Index names are explicit and stable (``<collection>_<fields>[_uq|_ttl]``) so
``create_index`` is a no-op on re-runs and tests can look indexes up by name.

The LangGraph checkpointer collections (``checkpoints``, ``checkpoint_writes``)
are deliberately absent: ``MongoDBSaver`` creates and owns their indexes.

Partial unique indexes: ``vpa`` on ``accounts`` / ``counterparties`` and
``email`` on ``users`` are optional fields (the validators allow them to be
absent). A plain unique index treats every missing value as ``null`` and would
reject the second document without the field, so these indexes carry a
``partialFilterExpression`` of ``{"<field>": {"$type": "string"}}``. That is
preferred over ``sparse`` because it also excludes explicit ``null`` values and
states the indexed shape exactly.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pymongo import ASCENDING, DESCENDING

from backend.app.repositories.mongo.collection_names import OperationalCollection as Col
from backend.app.repositories.mongo.collection_names import TruthCollection

IndexKeys = tuple[tuple[str, int], ...]
"""Ordered ``(field, direction)`` pairs, as accepted by ``create_index``."""


@dataclass(frozen=True, slots=True)
class IndexSpec:
    """One named index on one collection.

    Attributes:
        collection: Collection name, taken from ``collection_names``.
        name: Explicit, stable index name.
        keys: Ordered ``(field, direction)`` pairs.
        unique: Whether the index enforces uniqueness.
        ttl_seconds: ``expireAfterSeconds`` for a TTL index, else ``None``.
        partial_filter: ``partialFilterExpression``, else ``None``.
    """

    collection: str
    name: str
    keys: IndexKeys
    unique: bool = False
    ttl_seconds: int | None = None
    partial_filter: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        """Reject specs MongoDB would refuse or that are meaningless.

        Raises:
            ValueError: If keys are empty, or the TTL is non-positive or set on
                a compound index.
        """
        if not self.keys:
            raise ValueError(f"index {self.name!r} has no keys")
        if self.ttl_seconds is not None:
            if self.ttl_seconds <= 0:
                raise ValueError(f"index {self.name!r} TTL must be positive")
            if len(self.keys) != 1:
                raise ValueError(f"TTL index {self.name!r} must be single-field")


def _asc(*fields: str) -> IndexKeys:
    """Build ascending keys for the given fields."""
    return tuple((field, ASCENDING) for field in fields)


def _string_present(field: str) -> Mapping[str, Any]:
    """Partial filter that indexes only documents where ``field`` is a string."""
    return MappingProxyType({field: {"$type": "string"}})


def _static_operational_plan() -> tuple[IndexSpec, ...]:
    """Every operational index whose options do not depend on configuration."""
    return (
        IndexSpec(Col.CUSTOMERS, "customers_risk_rating", _asc("risk_rating")),
        IndexSpec(Col.ACCOUNTS, "accounts_customer_id", _asc("customer_id")),
        IndexSpec(Col.ACCOUNTS, "accounts_account_no_uq", _asc("account_no"), unique=True),
        IndexSpec(
            Col.ACCOUNTS,
            "accounts_vpa_uq",
            _asc("vpa"),
            unique=True,
            partial_filter=_string_present("vpa"),
        ),
        IndexSpec(
            Col.COUNTERPARTIES,
            "counterparties_vpa_uq",
            _asc("vpa"),
            unique=True,
            partial_filter=_string_present("vpa"),
        ),
        IndexSpec(Col.TRANSACTIONS, "transactions_account_id_ts", _asc("account_id", "ts")),
        IndexSpec(
            Col.TRANSACTIONS,
            "transactions_counterparty_ref_id_ts",
            _asc("counterparty.ref_id", "ts"),
        ),
        IndexSpec(Col.TRANSACTIONS, "transactions_transfer_id", _asc("transfer_id")),
        IndexSpec(Col.COMPLAINTS, "complaints_beneficiary_ref", _asc("beneficiary_ref")),
        IndexSpec(Col.COMPLAINTS, "complaints_linked_transfer_ids", _asc("linked_transfer_ids")),
        IndexSpec(
            Col.USERS,
            "users_email_uq",
            _asc("email"),
            unique=True,
            partial_filter=_string_present("email"),
        ),
        IndexSpec(Col.ALERTS, "alerts_dedupe_key_uq", _asc("dedupe_key"), unique=True),
        IndexSpec(Col.ALERTS, "alerts_status_priority", _asc("status", "priority")),
        IndexSpec(Col.ALERTS, "alerts_account_id", _asc("account_id")),
        IndexSpec(
            Col.CASES, "cases_status_priority_sla_due_at", _asc("status", "priority", "sla_due_at")
        ),
        IndexSpec(Col.CASES, "cases_alert_id_uq", _asc("alert_id"), unique=True),
        IndexSpec(Col.CASES, "cases_assigned_to", _asc("assigned_to")),
        IndexSpec(
            Col.CASE_RUNS,
            "case_runs_case_id_started_at",
            (("case_id", ASCENDING), ("started_at", DESCENDING)),
        ),
        IndexSpec(
            Col.NODE_EXECUTIONS, "node_executions_run_id_started_at", _asc("run_id", "started_at")
        ),
        IndexSpec(Col.EVIDENCE, "evidence_case_id_run_id", _asc("case_id", "run_id")),
        IndexSpec(
            Col.REPORTS,
            "reports_case_id_version",
            (("case_id", ASCENDING), ("version", DESCENDING)),
        ),
        IndexSpec(Col.ACTIONS, "actions_case_id_status", _asc("case_id", "status")),
        IndexSpec(Col.ACTIONS, "actions_status_due_at", _asc("status", "due_at")),
        IndexSpec(Col.DECISIONS, "decisions_case_id_created_at", _asc("case_id", "created_at")),
        IndexSpec(Col.AUDIT_LOGS, "audit_logs_case_id_ts", _asc("case_id", "ts")),
        IndexSpec(
            Col.AUDIT_LOGS, "audit_logs_entity_type_entity_id", _asc("entity.type", "entity.id")
        ),
        IndexSpec(Col.AUDIT_LOGS, "audit_logs_ts", _asc("ts")),
        IndexSpec(Col.LLM_CACHE, "llm_cache_key_uq", _asc("key"), unique=True),
        IndexSpec(Col.EVAL_RUNS, "eval_runs_run_id", _asc("run_id")),
        IndexSpec(Col.EVAL_RESULTS, "eval_results_run_id", _asc("run_id")),
        # dataset_meta: no secondary indexes.
    )


def operational_index_plan(llm_cache_ttl_seconds: int) -> tuple[IndexSpec, ...]:
    """Return the full operational index plan.

    Args:
        llm_cache_ttl_seconds: ``expireAfterSeconds`` for the ``llm_cache``
            ``created_at`` TTL index, sourced from ``LlmConfig.cache_ttl_seconds``.

    Returns:
        Every named index for the ``mulescope`` database, in creation order.

    Raises:
        ValueError: If ``llm_cache_ttl_seconds`` is not positive.
    """
    if llm_cache_ttl_seconds <= 0:
        raise ValueError("llm_cache_ttl_seconds must be positive")
    ttl = IndexSpec(
        Col.LLM_CACHE,
        "llm_cache_created_at_ttl",
        _asc("created_at"),
        ttl_seconds=llm_cache_ttl_seconds,
    )
    return (*_static_operational_plan(), ttl)


TRUTH_INDEX_PLAN: tuple[IndexSpec, ...] = (
    IndexSpec(TruthCollection.GROUND_TRUTH, "ground_truth_account_id", _asc("account_id")),
    IndexSpec(TruthCollection.GROUND_TRUTH, "ground_truth_scenario_type", _asc("scenario_type")),
)
"""Indexes for the ``mulescope_truth`` database (datagen/evals only)."""
