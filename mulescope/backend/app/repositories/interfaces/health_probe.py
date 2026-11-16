"""Port for checking that the operational datastore is reachable.

Implemented by ``repositories.mongo.health_probe.MongoHealthProbe`` and
consumed by ``services.system_service.SystemService``. The protocol carries no
database types, so the service layer never imports PyMongo.
"""

from __future__ import annotations

from typing import Protocol

__all__ = ["HealthProbe"]


class HealthProbe(Protocol):
    """A lightweight liveness check against a backing dependency."""

    async def ping(self) -> None:
        """Check that the dependency answers.

        Raises:
            DependencyUnavailable: If the dependency cannot be reached or
                rejects the check.
        """
        ...
