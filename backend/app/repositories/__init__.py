"""Repository layer: all MongoDB access, one class per collection.

``interfaces`` defines the abstract ports services depend on; ``mongo``
provides the PyMongo implementations and collection bootstrapping. Wired by
``core.container``; services see only the interfaces.
"""
