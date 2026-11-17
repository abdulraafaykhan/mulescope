"""Graph nodes: one module per node, each doing one thing.

Registered on the ``StateGraph`` by ``graph.builder``. Nodes call services,
agents and repository ports injected through ``RunnableConfig``. Populated
from M4 onward.
"""
