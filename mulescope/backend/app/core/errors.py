"""Domain error hierarchy shared by every layer.

These exceptions describe *what* went wrong in domain terms. They carry no HTTP
knowledge: the single mapping from exception type to status code and error
envelope lives in ``backend/app/api/error_handlers.py``. Services, repositories,
graph nodes and the CLIs raise these; only the API layer translates them.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DependencyUnavailable",
    "DomainError",
    "LLMUnavailable",
    "NotFound",
    "PolicyViolation",
]


class DomainError(Exception):
    """Base class for every expected, domain-level failure.

    Attributes:
        message: Human-readable description of the failure, safe to show to a
            client. Must never contain secrets.
        detail: Optional structured context (for example the missing entity id).
            Must be JSON-serialisable so the API layer can place it in the error
            envelope unchanged.
    """

    def __init__(self, message: str, detail: Any | None = None) -> None:
        """Initialise the error.

        Args:
            message: Human-readable description of the failure.
            detail: Optional JSON-serialisable structured context.
        """
        super().__init__(message)
        self.message: str = message
        self.detail: Any | None = detail

    def __repr__(self) -> str:
        """Return a debug representation including message and detail."""
        return f"{type(self).__name__}(message={self.message!r}, detail={self.detail!r})"


class NotFound(DomainError):  # noqa: N818 - names fixed by the design
    """A requested entity (case, alert, account, ...) does not exist."""


class PolicyViolation(DomainError):  # noqa: N818 - names fixed by the design
    """An operation would break a domain policy or state-machine rule."""


class LLMUnavailable(DomainError):  # noqa: N818 - names fixed by the design
    """No LLM provider could serve the request and no fallback applies."""


class DependencyUnavailable(DomainError):  # noqa: N818 - names fixed by the design
    """An infrastructure dependency (for example MongoDB or a config file) failed."""
