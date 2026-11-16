"""Request and response DTOs, kept separate from domain entities.

Used by routers and the error handlers to define the public API contract,
which also feeds the frontend's generated OpenAPI types. May import the domain
layer only.
"""
