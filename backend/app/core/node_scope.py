"""The graph node that is running right now, for code far below the node.

``graph/instrument.py`` binds a :class:`NodeScope` around every node, and
``llm/call_recorder.py`` reads it to label each LLM call attempt with its case,
run, node and agent. A ``ContextVar`` keeps the parallel Profiler and Flow
Analyst branches apart and avoids threading ids through every agent signature.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

__all__ = ["NodeScope", "bind_node_scope", "current_node_scope"]


@dataclass(frozen=True, slots=True)
class NodeScope:
    """Identity of one node execution.

    Attributes:
        case_id: Case being investigated.
        run_id: Graph run.
        node: Node name as registered in the graph.
        agent: Agent key of the node (``code``, ``profiler``, ``flow``, ...).
        node_exec_id: Id of the ``node_executions`` row of this execution.
    """

    case_id: str | None
    run_id: str | None
    node: str
    agent: str
    node_exec_id: str | None


_scope_var: ContextVar[NodeScope | None] = ContextVar("node_scope", default=None)


@contextmanager
def bind_node_scope(scope: NodeScope) -> Iterator[None]:
    """Make ``scope`` the current node scope for the body of the block.

    Args:
        scope: The node execution that is starting.

    Yields:
        Nothing; the previous scope is restored on exit.
    """
    token = _scope_var.set(scope)
    try:
        yield
    finally:
        _scope_var.reset(token)


def current_node_scope() -> NodeScope | None:
    """Return the node scope bound by the caller, or ``None`` outside a node."""
    return _scope_var.get()
