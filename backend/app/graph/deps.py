"""Dependencies handed to graph nodes through ``RunnableConfig``.

Built once by ``core/wiring.py``; passed as ``config["configurable"]["deps"]``
so nodes never import a database client (dependency inversion).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig

from backend.app.core.clock import Clock
from backend.app.domain.policy.config import PlaybookConfig, ScoringConfig


@dataclass
class GraphDeps:
    """Everything a node may use. All repositories are narrow ports."""

    clock: Clock
    scoring: ScoringConfig
    playbook: PlaybookConfig
    metrics: Any  # MetricsService
    tx: Any  # MongoTransactionRepository (read-only)
    accounts: Any
    customers: Any
    complaints: Any
    alerts: Any
    cases: Any
    counters: Any
    evidence: Any
    reports: Any
    actions: Any
    decisions: Any
    runs: Any
    node_execs: Any
    llm_calls: Any  # MongoLlmCallRepository (finalize reads the run's estimated cost)
    audit: Any
    agents: Any  # AgentSuite (template or LLM)


def deps_of(config: RunnableConfig) -> GraphDeps:
    """Return the deps injected for this run."""
    deps: GraphDeps = config["configurable"]["deps"]
    return deps
