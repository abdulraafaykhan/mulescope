"""Builds repositories, services and the compiled graph onto the container.

Called once from ``Container.startup`` after the clients and checkpointer
exist. Also used by scripts (``uv run smoke``) through ``build_app_objects``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from backend.app.agents.suite import AgentSuite
from backend.app.core.clock import Clock, SystemClock
from backend.app.core.config_files import load_playbook_config, load_scoring_config
from backend.app.graph.builder import build_graph
from backend.app.graph.deps import GraphDeps
from backend.app.repositories.mongo.accounts_repo import MongoAccountRepository, MongoComplaintRepository, MongoCounterpartyRepository, MongoCustomerRepository
from backend.app.repositories.mongo.alerts_repo import MongoAlertRepository
from backend.app.repositories.mongo.audit_repo import MongoAuditRepository
from backend.app.repositories.mongo.case_records_repo import (
    MongoActionRepository,
    MongoCounterRepository,
    MongoDecisionRepository,
    MongoEvalRepository,
    MongoEvidenceRepository,
    MongoNodeExecutionRepository,
    MongoReportRepository,
    MongoRunRepository,
)
from backend.app.repositories.mongo.cases_repo import MongoCaseRepository
from backend.app.repositories.mongo.transactions_repo import MongoTransactionRepository
from backend.app.services.action_service import ActionService
from backend.app.services.case_query import CaseQueryService
from backend.app.services.case_runner import CaseRunner
from backend.app.services.detection import PassThroughDetector
from backend.app.services.event_bus import RunEventBus
from backend.app.services.metrics_service import MetricsService

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

    from backend.app.core.container import Container


@dataclass
class AppObjects:
    """Everything the routes and scripts use."""

    deps: GraphDeps
    graph: Any
    runner: CaseRunner
    query: CaseQueryService
    actions: ActionService
    detector: PassThroughDetector
    bus: RunEventBus
    audit: MongoAuditRepository
    evals: MongoEvalRepository
    alerts: MongoAlertRepository
    counterparties: MongoCounterpartyRepository


def build_app_objects(db: AsyncDatabase[Any], checkpointer: Any, *, config_dir: Any, graph_version: str, llm_mode: str, clock: Clock | None = None) -> AppObjects:
    """Wire repositories, services and the graph for one database."""
    clock = clock or SystemClock()
    scoring = load_scoring_config(config_dir)
    playbook = load_playbook_config(config_dir)
    tx = MongoTransactionRepository(db)
    accounts, customers, complaints = MongoAccountRepository(db), MongoCustomerRepository(db), MongoComplaintRepository(db)
    alerts, cases = MongoAlertRepository(db), MongoCaseRepository(db)
    audit = MongoAuditRepository(db)
    runs, node_execs = MongoRunRepository(db), MongoNodeExecutionRepository(db)
    deps = GraphDeps(
        clock=clock, scoring=scoring, playbook=playbook, metrics=MetricsService(tx, accounts, customers, complaints, scoring), tx=tx,
        accounts=accounts, customers=customers, complaints=complaints, alerts=alerts, cases=cases, counters=MongoCounterRepository(db),
        evidence=MongoEvidenceRepository(db), reports=MongoReportRepository(db), actions=MongoActionRepository(db), decisions=MongoDecisionRepository(db),
        runs=runs, node_execs=node_execs, audit=audit, agents=AgentSuite(),
    )
    graph = build_graph(checkpointer)
    bus = RunEventBus()
    runner = CaseRunner(graph, deps, bus, graph_version, llm_mode, dataset_seed=None)
    query = CaseQueryService(cases=cases, alerts=alerts, accounts=accounts, customers=customers, tx=tx, evidence=deps.evidence, reports=deps.reports, actions=deps.actions, decisions=deps.decisions, runs=runs, node_execs=node_execs, complaints=complaints, clock=clock)
    return AppObjects(
        deps=deps, graph=graph, runner=runner, query=query, actions=ActionService(deps.actions, audit, clock),
        detector=PassThroughDetector(tx, alerts, cases, scoring, playbook, clock), bus=bus, audit=audit, evals=MongoEvalRepository(db), alerts=alerts,
        counterparties=MongoCounterpartyRepository(db),
    )


async def wire(container: Container) -> None:
    """Attach application objects to ``container.extras['app']``."""
    s = container.settings
    container.extras["app"] = build_app_objects(container.db, container.checkpointer, config_dir=s.config_dir, graph_version=s.graph_version, llm_mode=s.llm_mode.value)
