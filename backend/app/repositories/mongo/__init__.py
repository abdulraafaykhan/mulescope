"""MongoDB implementations of the repository ports, plus collection bootstrapping.

Uses the native async PyMongo client. Holds the ``$jsonSchema`` validators,
the declarative index plan and ``ensure_collections``. Constructed only by
``core.container`` (and ``datagen`` for the truth database); never imported by
routers or domain code.
"""
