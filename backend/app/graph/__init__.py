"""LangGraph wiring: state, nodes, edges, builder and checkpointer.

``builder.py`` compiles the graph once and ``checkpoint.py`` builds the
``MongoDBSaver``; both are called by ``core.container`` at startup. Nodes
receive dependencies through ``RunnableConfig``, never through globals.
"""
