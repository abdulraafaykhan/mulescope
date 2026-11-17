"""In-process event bus: one stream of progress events per case run.

The case runner publishes graph events here; the SSE endpoint replays the
history and then follows new events. In-memory on purpose (single API
process); history is lost on restart, but run state is not (checkpointer).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

TERMINAL = {"run_completed", "run_failed", "interrupt"}
HISTORY_LIMIT = 500


class RunEventBus:
    """Publish/subscribe per ``run_id`` with replay."""

    def __init__(self) -> None:
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._subs: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        history = self._history[run_id]
        history.append(event)
        del history[:-HISTORY_LIMIT]
        for q in list(self._subs[run_id]):
            q.put_nowait(event)

    async def subscribe(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield past events, then new ones until a terminal event."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subs[run_id].append(q)
        try:
            for event in list(self._history[run_id]):
                yield event
            last = self._history[run_id][-1]["type"] if self._history[run_id] else None
            if last == "run_completed" or last == "run_failed":
                return
            while True:
                event = await q.get()
                yield event
                if event["type"] in ("run_completed", "run_failed"):
                    return
        finally:
            self._subs[run_id].remove(q)
