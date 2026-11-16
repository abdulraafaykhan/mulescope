"""LangGraph checkpointer factory backed by MongoDB.

Called once by the composition root (``core/container.py``) during startup. The
returned saver is handed to :func:`backend.app.graph.builder.build_graph`.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient

__all__ = ["build_checkpointer"]


def build_checkpointer(
    sync_client: MongoClient[dict[str, Any]], db_name: str, ttl_seconds: int
) -> MongoDBSaver:
    """Build the MongoDB checkpointer for the compiled graph.

    The saver owns the ``checkpoints`` and ``checkpoint_writes`` collections.
    With ``ttl`` set it stamps a BSON ``created_at`` on every document and
    creates, on both collections, a unique compound index plus a
    ``created_at`` TTL index with ``expireAfterSeconds=ttl_seconds``. Our own
    bootstrap never touches these collections.

    ``MongoDBSaver.__init__`` creates those indexes synchronously and blocks on
    network I/O, so callers in async code must run this function through
    ``asyncio.to_thread``.

    Args:
        sync_client: The dedicated synchronous client, used only by the saver.
        db_name: Operational database name that holds the checkpoint
            collections.
        ttl_seconds: Checkpoint retention in seconds (from
            ``settings.checkpoint_ttl_seconds``).

    Returns:
        A ready :class:`MongoDBSaver`.

    Raises:
        ValueError: If ``ttl_seconds`` is not positive.
    """
    if ttl_seconds <= 0:
        raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")
    return MongoDBSaver(client=sync_client, db_name=db_name, ttl=ttl_seconds)
