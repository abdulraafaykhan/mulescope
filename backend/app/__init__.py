"""MuleScope API application.

Contains the layered backend: ``core`` (settings, container, logging, errors,
clock), ``domain``, ``repositories``, ``services``, ``agents``, ``graph``,
``llm`` and ``api``. The ``uv run dev`` script calls ``backend.app.main:run``,
and tests import the app factory from ``backend.app.main``.
"""
