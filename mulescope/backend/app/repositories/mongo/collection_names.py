"""Single source of MongoDB collection names.

Every collection name used by validators, the index plan, bootstrapping and the
repositories comes from here, so a name is spelled exactly once. Imported by
``repositories.mongo`` modules and by tests.

The LangGraph checkpointer collections (``checkpoints``, ``checkpoint_writes``)
are deliberately absent: they are owned and managed by ``MongoDBSaver``.
"""

from enum import StrEnum, unique


@unique
class OperationalCollection(StrEnum):
    """Collections in the operational ``mulescope`` database."""

    CUSTOMERS = "customers"
    ACCOUNTS = "accounts"
    COUNTERPARTIES = "counterparties"
    TRANSACTIONS = "transactions"
    COMPLAINTS = "complaints"
    USERS = "users"
    ALERTS = "alerts"
    CASES = "cases"
    CASE_RUNS = "case_runs"
    NODE_EXECUTIONS = "node_executions"
    EVIDENCE = "evidence"
    REPORTS = "reports"
    ACTIONS = "actions"
    DECISIONS = "decisions"
    AUDIT_LOGS = "audit_logs"
    LLM_CACHE = "llm_cache"
    EVAL_RUNS = "eval_runs"
    EVAL_RESULTS = "eval_results"
    DATASET_META = "dataset_meta"


@unique
class TruthCollection(StrEnum):
    """Collections in the truth ``mulescope_truth`` database (datagen/evals only)."""

    GROUND_TRUTH = "ground_truth"
