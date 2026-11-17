"""Unit tests for ``backend.app.core.logging``.

Every emitted line must be valid JSON and carry ``case_id`` and ``run_id``,
both inside and outside ``bind_run_context``. Each test writes to its own
``StringIO`` and the root logger is restored afterwards.

**Validates: Requirements 7.1, 7.2**
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from backend.app.core.logging import bind_run_context, configure_logging, get_logger

pytestmark = pytest.mark.unit


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    """Configure JSON logging into a StringIO and restore the root logger after."""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    buffer = io.StringIO()
    configure_logging(logging.DEBUG, stream=buffer)
    try:
        yield buffer
    finally:
        for handler in list(root.handlers):
            if handler not in saved_handlers:
                root.removeHandler(handler)
                handler.close()
        for handler in saved_handlers:
            if handler not in root.handlers:
                root.addHandler(handler)
        root.setLevel(saved_level)


def _lines(buffer: io.StringIO) -> list[dict[str, Any]]:
    raw = [line for line in buffer.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in raw]


def test_line_outside_context_has_null_ids(stream: io.StringIO) -> None:
    get_logger("test.outside").info("hello")
    (line,) = _lines(stream)
    assert line["message"] == "hello"
    assert line["level"] == "INFO"
    assert line["logger"] == "test.outside"
    assert "ts" in line
    assert line["case_id"] is None
    assert line["run_id"] is None


def test_line_inside_context_carries_ids(stream: io.StringIO) -> None:
    log = get_logger("test.inside")
    with bind_run_context("CASE-1", "RUN-1"):
        log.info("bound")
    log.info("unbound")
    bound, unbound = _lines(stream)
    assert bound["case_id"] == "CASE-1"
    assert bound["run_id"] == "RUN-1"
    assert unbound["case_id"] is None
    assert unbound["run_id"] is None


def test_nested_contexts_restore_previous(stream: io.StringIO) -> None:
    log = get_logger("test.nested")
    with bind_run_context("CASE-A", "RUN-A"):
        with bind_run_context("CASE-B", None):
            log.info("inner")
        log.info("outer")
    inner, outer = _lines(stream)
    assert (inner["case_id"], inner["run_id"]) == ("CASE-B", None)
    assert (outer["case_id"], outer["run_id"]) == ("CASE-A", "RUN-A")


def test_every_level_extra_and_exception_is_json(stream: io.StringIO) -> None:
    log = get_logger("test.levels")
    log.debug("d")
    log.warning("w", extra={"collection": "alerts", "count": 3})
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("failed")
    lines = _lines(stream)
    assert len(lines) == 3
    for line in lines:
        assert "case_id" in line
        assert "run_id" in line
    assert lines[1]["collection"] == "alerts"
    assert lines[1]["count"] == 3
    assert "ValueError: boom" in lines[2]["exc_info"]


def test_configure_logging_is_idempotent(stream: io.StringIO) -> None:
    configure_logging(logging.INFO, stream=stream)
    get_logger("test.idempotent").info("once")
    assert len(_lines(stream)) == 1
