"""Builds repositories, services and the compiled graph onto the container.

Called once from ``Container.startup`` after the clients and checkpointer
exist. Also used by scripts (``uv run smoke``) through ``build_app_objects``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from backend.app.core.clock import Clock, SystemClock
from backend.app.core.config_files import (
    LlmConfig,
    load_llm_config,
    load_playbook_config,
    load_scoring_config,
)
from backend.app.graph.builder import build_graph
from backend.app.graph.deps import GraphDeps
from backend.app.llm.factory import build_agent_suite
from backend.app.repositories.mongo.accounts_repo import (
    MongoAccountRepository,
    MongoComplaintRepository,
    MongoCounterpartyRepository,
    MongoCustomerRepository,
)
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
from backend.app.repositories.mongo.llm_cache_repo import MongoLlmCacheRepository
from backend.app.repositories.mongo.llm_calls_repo import MongoLlmCallRepository
from backend.app.repositories.mongo.transactions_repo import MongoTransactionRepository
from backend.app.services.action_service import ActionService
from backend.app.services.case_query import CaseQueryService
from backend.app.services.case_runner import CaseRunner
from backend.app.services.detection import PassThroughDetector
from backend.app.services.event_bus import RunEventBus
from backend.app.services.metrics_service import MetricsService
from backend.app.services.observability_service import ObservabilityService

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
    observability: ObservabilityService


def build_app_objects(
    db: AsyncDatabase[Any], checkpointer: Any, *, config_dir: Any, graph_version: str, llm_mode: str, clock: Clock | None = None,
    groq_key: str | None = None, gemini_key: str | None = None, llm_config: LlmConfig | None = None,
) -> AppObjects:
    """Wire repositories, services, agents and the graph for one database.

    In live mode the agents call Groq / Gemini for every provider whose key is
    given; otherwise (and per call on any LLM failure) they use templates.
    """
    clock = clock or SystemClock()
    scoring = load_scoring_config(config_dir)
    playbook = load_playbook_config(config_dir)
    llm_cfg = llm_config or load_llm_config(config_dir)
    llm_calls = MongoLlmCallRepository(db)
    agents = build_agent_suite(
        llm_mode=llm_mode,
        cfg=llm_cfg,
        groq_key=groq_key,
        gemini_key=gemini_key,
        cache=MongoLlmCacheRepository(db),
        call_log=llm_calls,
        clock=clock,
        str_sections=list(playbook.str_required_sections),
        tipping_terms=list(playbook.tipping_off_terms),
    )
    tx = MongoTransactionRepository(db)
    accounts, customers, complaints = MongoAccountRepository(db), MongoCustomerRepository(db), MongoComplaintRepository(db)
    alerts, cases = MongoAlertRepository(db), MongoCaseRepository(db)
    audit = MongoAuditRepository(db)
    runs, node_execs = MongoRunRepository(db), MongoNodeExecutionRepository(db)
    deps = GraphDeps(
        clock=clock, scoring=scoring, playbook=playbook, metrics=MetricsService(tx, accounts, customers, complaints, scoring), tx=tx,
        accounts=accounts, customers=customers, complaints=complaints, alerts=alerts, cases=cases, counters=MongoCounterRepository(db),
        evidence=MongoEvidenceRepository(db), reports=MongoReportRepository(db), actions=MongoActionRepository(db), decisions=MongoDecisionRepository(db),
        runs=runs, node_execs=node_execs, llm_calls=llm_calls, audit=audit, agents=agents,
    )
    graph = build_graph(checkpointer)
    bus = RunEventBus()
    runner = CaseRunner(graph, deps, bus, graph_version, llm_mode, dataset_seed=None)
    query = CaseQueryService(cases=cases, alerts=alerts, accounts=accounts, customers=customers, tx=tx, evidence=deps.evidence, reports=deps.reports, actions=deps.actions, decisions=deps.decisions, runs=runs, node_execs=node_execs, complaints=complaints, clock=clock)
    return AppObjects(
        deps=deps, graph=graph, runner=runner, query=query, actions=ActionService(deps.actions, audit, clock),
        detector=PassThroughDetector(tx, alerts, cases, scoring, playbook, clock), bus=bus, audit=audit, evals=MongoEvalRepository(db), alerts=alerts,
        counterparties=MongoCounterpartyRepository(db),
        observability=ObservabilityService(
            calls=llm_calls, runs=runs, node_execs=node_execs, models=llm_cfg.models,
            retention=timedelta(seconds=llm_cfg.call_log_ttl_seconds), clock=clock,
        ),
    )


def secret(value: Any) -> str | None:
    """``SecretStr | None`` -> plain string at the point of use (never logged)."""
    return value.get_secret_value() if value is not None else None


async def wire(container: Container) -> None:
    """Attach application objects to ``container.extras['app']``."""
    s = container.settings
    container.extras["app"] = build_app_objects(
        container.db, container.checkpointer, config_dir=s.config_dir, graph_version=s.graph_version, llm_mode=s.llm_mode.value,
        groq_key=secret(s.groq_api_key), gemini_key=secret(s.gemini_api_key), llm_config=container.llm_config,
    )
