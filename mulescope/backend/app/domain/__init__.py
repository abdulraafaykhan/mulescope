"""Domain layer: entities, enums, value objects and pure functions.

Imported by every other layer (repositories, services, agents, graph, API
schemas). It may import only the stdlib and pydantic; it must never import
FastAPI, PyMongo or LangGraph.
"""
