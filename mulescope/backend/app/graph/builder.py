"""Investigation graph builder.

Called once by the composition root (``core/container.py``) at startup to
compile the graph with the MongoDB checkpointer. M0 compiles a trivial
placeholder so the wiring and ``thread_id`` plumbing exist; the real nodes
arrive in M4.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

__all__ = ["PLACEHOLDER_NODE", "PlaceholderState", "build_graph", "passthrough"]

PLACEHOLDER_NODE = "passthrough"
"""Name of the single placeholder node."""


class PlaceholderState(TypedDict, total=False):
    """Placeholder graph state. Replaced by the investigation state in M4.

    Attributes:
        case_id: Identifier of the case under investigation.
    """

    case_id: str


def passthrough(state: PlaceholderState) -> PlaceholderState:
    """Return no updates, leaving the state unchanged.

    Args:
        state: Current graph state.

    Returns:
        An empty update.
    """
    return {}


def build_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[PlaceholderState, None, PlaceholderState, PlaceholderState]:
    """Compile the placeholder graph with the given checkpointer.

    Pure: performs no I/O beyond what ``compile`` does.

    Args:
        checkpointer: The saver used to persist graph state per ``thread_id``.

    Returns:
        The compiled graph: ``START -> passthrough -> END``.
    """
    builder = StateGraph(PlaceholderState)
    builder.add_node(PLACEHOLDER_NODE, passthrough)
    builder.add_edge(START, PLACEHOLDER_NODE)
    builder.add_edge(PLACEHOLDER_NODE, END)
    return builder.compile(checkpointer=checkpointer)
