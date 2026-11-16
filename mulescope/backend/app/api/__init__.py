"""HTTP layer: routers, request/response schemas, dependency providers and error handlers.

Mounted by ``backend.app.main.create_app``. Routers are thin: validate input,
call one service obtained through ``deps``, return a schema.
"""
