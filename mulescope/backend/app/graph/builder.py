"""Builds and compiles the investigation graph (section 7). Compiled once at startup.

    load_case -> compute_metrics -> [profiler || flow_analyst] -> aggregate_evidence
      -> sufficiency_check --(gaps, max 1)--> flow_analyst
      -> score_and_policy -> plan_actions -> narrative_writer -> critic
      --(issues, max 1)--> narrative_writer
      -> analyst_gate [INTERRUPT] -> apply_decision
           approve/edit/override -> execute_actions -> finalize
           request_more          -> flow_analyst (max 1)
           reject                -> finalize

The separate reviewer gate is skipped in this build (see PROGRESS.md).
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.app.graph import edges
from backend.app.graph.nodes.decide import critic, narrative_writer, plan_actions, score_and_policy
from backend.app.graph.nodes.investigate import aggregate_evidence, compute_metrics, flow_analyst, load_case, profiler, sufficiency_check
from backend.app.graph.nodes.review import analyst_gate, apply_decision, execute_actions, finalize
from backend.app.graph.state import CaseState

GRAPH_NODES = (
    "load_case", "compute_metrics", "profiler", "flow_analyst", "aggregate_evidence", "sufficiency_check", "score_and_policy",
    "plan_actions", "narrative_writer", "critic", "analyst_gate", "apply_decision", "execute_actions", "finalize",
)


def build_graph(checkpointer: BaseCheckpointSaver[Any]) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Compile the case graph with the given checkpointer."""
    g = StateGraph(CaseState)
    for name, fn in (
        ("load_case", load_case), ("compute_metrics", compute_metrics), ("profiler", profiler), ("flow_analyst", flow_analyst),
        ("aggregate_evidence", aggregate_evidence), ("sufficiency_check", sufficiency_check), ("score_and_policy", score_and_policy),
        ("plan_actions", plan_actions), ("narrative_writer", narrative_writer), ("critic", critic), ("analyst_gate", analyst_gate),
        ("apply_decision", apply_decision), ("execute_actions", execute_actions), ("finalize", finalize),
    ):
        g.add_node(name, fn)
    g.add_edge(START, "load_case")
    g.add_edge("load_case", "compute_metrics")
    g.add_edge("compute_metrics", "profiler")
    g.add_edge("compute_metrics", "flow_analyst")
    g.add_edge("profiler", "aggregate_evidence")
    g.add_edge("flow_analyst", "aggregate_evidence")
    g.add_edge("aggregate_evidence", "sufficiency_check")
    g.add_conditional_edges("sufficiency_check", edges.after_sufficiency, ["flow_analyst", "score_and_policy"])
    g.add_edge("score_and_policy", "plan_actions")
    g.add_edge("plan_actions", "narrative_writer")
    g.add_edge("narrative_writer", "critic")
    g.add_conditional_edges("critic", edges.after_critic, ["narrative_writer", "analyst_gate"])
    g.add_edge("analyst_gate", "apply_decision")
    g.add_conditional_edges("apply_decision", edges.after_decision, ["flow_analyst", "execute_actions", "finalize"])
    g.add_edge("execute_actions", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
