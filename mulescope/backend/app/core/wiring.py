"""Builds repositories, services and the compiled graph onto the container.

Called once from ``Container.startup`` after the clients and checkpointer exist.
Kept separate from ``container.py`` so the client lifecycle and the object graph
are each easy to read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.core.container import Container


async def wire(container: Container) -> None:
    """Attach application objects to ``container.extras``.

    Args:
        container: A started container with ``db`` and ``checkpointer`` ready.
    """
    return None
