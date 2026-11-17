"""Structured JSON logging for every MuleScope process.

The API, datagen and evals entry points call ``configure_logging`` once at
startup; every other module obtains its logger through ``get_logger``. Each
emitted line is a single JSON object that always carries ``case_id`` and
``run_id`` (``null`` when unset). Those values are held in ``contextvars`` and
set for the duration of a run with ``bind_run_context``, so they propagate
across ``await`` points and into tasks spawned within the bound context.

This module is named ``logging`` inside the ``backend.app.core`` package; the
absolute ``import logging`` below resolves to the standard library, not to this
file.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Final, TextIO

__all__ = [
    "JsonFormatter",
    "bind_run_context",
    "configure_logging",
    "get_logger",
]

_case_id_var: ContextVar[str | None] = ContextVar("case_id", default=None)
_run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)

# Attribute set on the handler we install, so repeat configuration replaces it
# instead of stacking duplicates.
_HANDLER_MARKER: Final[str] = "_mulescope_json_handler"

# Attributes present on every ``LogRecord``; anything else came from ``extra=``.
_RESERVED_RECORD_ATTRS: Final[frozenset[str]] = frozenset(
    vars(logging.LogRecord("", logging.NOTSET, "", 0, "", None, None))
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Formats a ``LogRecord`` as one JSON object per line.

    Every line has ``ts`` (ISO-8601 UTC), ``level``, ``logger``, ``message``,
    ``case_id`` and ``run_id``. Fields passed through ``extra=`` are included,
    and exception information is rendered under ``exc_info``. Values that are
    not JSON-serialisable are converted with ``str``.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render a record as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            A single-line JSON document.
        """
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "case_id": _case_id_var.get(),
            "run_id": _run_id_var.get(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: int | str = logging.INFO, stream: TextIO | None = None) -> None:
    """Install the JSON handler on the root logger.

    Idempotent: a handler previously installed by this function is removed
    before the new one is added, so repeated calls never duplicate output.
    Handlers installed by other code (for example pytest's capture) are left
    untouched.

    Args:
        level: Root log level, as a ``logging`` constant or name such as ``"INFO"``.
        stream: Destination stream. Defaults to ``sys.stderr``.
    """
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARKER, False):
            root.removeHandler(existing)
            existing.close()

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter())
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
    root.setLevel(level.upper() if isinstance(level, str) else level)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that emits through the configured JSON handler.

    Args:
        name: Logger name, conventionally ``__name__`` of the calling module.

    Returns:
        The standard-library logger for ``name``.
    """
    return logging.getLogger(name)


@contextmanager
def bind_run_context(case_id: str | None, run_id: str | None) -> Iterator[None]:
    """Bind ``case_id`` and ``run_id`` to every log line within the block.

    Previous values are restored on exit, so bindings nest correctly.

    Args:
        case_id: Case identifier (``CASE-...``), or ``None``.
        run_id: Run identifier (``RUN-...``), or ``None``.

    Yields:
        Nothing; the bindings are active for the body of the ``with`` block.
    """
    case_token = _case_id_var.set(case_id)
    run_token = _run_id_var.set(run_id)
    try:
        yield
    finally:
        _run_id_var.reset(run_token)
        _case_id_var.reset(case_token)
