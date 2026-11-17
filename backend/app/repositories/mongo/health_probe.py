"""MongoDB implementation of the :class:`HealthProbe` port.

Built by ``core.container`` with the operational database handle and handed to
``SystemService``. It runs the server ``ping`` command and translates PyMongo
failures into :class:`~backend.app.core.errors.DependencyUnavailable`, whose
message and detail never contain the connection string or host.
"""

from __future__ import annotations

from typing import Any, Final

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import ConnectionFailure, OperationFailure

from backend.app.core.errors import DependencyUnavailable

__all__ = ["MongoHealthProbe"]

_PING_ERRORS: Final[tuple[type[Exception], ...]] = (ConnectionFailure, OperationFailure)
"""Errors a ping can raise. ``ConnectionFailure`` covers server selection and
network timeouts and auto-reconnect; ``OperationFailure`` covers a server that
answers but rejects the command (for example an auth failure)."""


class MongoHealthProbe:
    """Pings the operational MongoDB database.

    Args:
        db: Handle to the operational ``mulescope`` database, owned by the
            container. The probe never creates or closes a client.
    """

    def __init__(self, db: AsyncDatabase[Any]) -> None:
        """Store the database handle.

        Args:
            db: Handle to the operational database.
        """
        self._db = db

    async def ping(self) -> None:
        """Run the ``ping`` command.

        Raises:
            DependencyUnavailable: If MongoDB is unreachable, times out, or
                rejects the command.
        """
        try:
            await self._db.command("ping")
        except _PING_ERRORS as exc:
            raise DependencyUnavailable(
                "MongoDB operational database is unreachable",
                detail={"dependency": "mongodb", "error_type": type(exc).__name__},
            ) from exc
