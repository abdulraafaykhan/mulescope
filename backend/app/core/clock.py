"""Single time source for the application.

Nothing outside this module calls ``datetime.now()`` or ``datetime.utcnow()``
directly. Services, repositories, graph nodes and the CLIs receive a ``Clock``
through their constructors (wired by the composition root), so tests can inject
a fixed clock and every stored timestamp is a timezone-aware UTC ``datetime``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

__all__ = ["Clock", "SystemClock"]


@runtime_checkable
class Clock(Protocol):
    """Port for obtaining the current time."""

    def now(self) -> datetime:
        """Return the current instant.

        Returns:
            A timezone-aware ``datetime`` in UTC.
        """
        ...


class SystemClock:
    """``Clock`` implementation backed by the system wall clock."""

    def now(self) -> datetime:
        """Return the current system time in UTC.

        Returns:
            A timezone-aware ``datetime`` whose ``tzinfo`` is ``UTC``.
        """
        return datetime.now(tz=UTC)
