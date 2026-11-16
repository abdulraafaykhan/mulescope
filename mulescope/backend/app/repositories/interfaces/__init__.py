"""Abstract repository ports (protocols) such as health probes and per-collection repositories.

Small, segregated interfaces that services and graph nodes depend on.
Implemented by ``repositories.mongo``; imported by services, agents and graph.
May import only the domain layer.
"""
