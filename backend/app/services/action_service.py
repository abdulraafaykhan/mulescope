"""Per-action analyst decisions: approve, reject (with reason) or reverse.

Rejected actions are skipped by ``execute_actions``; only executed reversible
actions can be reversed. Every change is audited.
"""

from __future__ import annotations

from typing import Any

from backend.app.core.clock import Clock
from backend.app.core.errors import NotFound, PolicyViolation

TRANSITIONS = {
    "approve": ({"proposed"}, "approved"),
    "reject": ({"proposed", "approved"}, "rejected"),
    "reverse": ({"executed"}, "reversed"),
}


class ActionService:
    """Applies one analyst operation to one action."""

    def __init__(self, actions: Any, audit: Any, clock: Clock) -> None:
        self._actions, self._audit, self._clock = actions, audit, clock

    async def change(self, action_id: str, op: str, user_id: str, reason: str | None) -> dict[str, Any]:
        action = await self._actions.get(action_id)
        if action is None:
            raise NotFound(f"action {action_id} not found")
        if op not in TRANSITIONS:
            raise PolicyViolation(f"unknown operation {op!r}", detail={"allowed": sorted(TRANSITIONS)})
        allowed_from, to = TRANSITIONS[op]
        if action["status"] not in allowed_from:
            raise PolicyViolation(f"cannot {op} an action that is {action['status']}")
        if op in ("reject", "reverse") and not (reason or "").strip():
            raise PolicyViolation(f"{op} requires a reason")
        if op == "reverse" and not action.get("reversible"):
            raise PolicyViolation("this action is not reversible")
        now = self._clock.now()
        fields: dict[str, Any] = {"status": to}
        if op == "approve":
            fields["approved_by"] = user_id
        updated = await self._actions.update(action_id, fields, {"ts": now, "status": to, "by": user_id, "reason": reason}, now)
        await self._audit.append(ts=now, actor={"type": "analyst", "id": user_id}, event=f"action.{op}", entity={"type": "action", "id": action_id}, case_id=action["case_id"], run_id=action.get("run_id"), payload={"type": action["type"], "reason": reason})
        return updated or {}
