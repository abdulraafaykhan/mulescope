"""Text helpers shared by the agents: INR with Indian grouping, IST dates,
citation tags and untrusted-data handling for transaction remarks.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

IST = timedelta(hours=5, minutes=30)
REMARK_MAX = 140
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_INJECTION = re.compile(r"ignore (all |any )?previous instructions|^system:|\bsystem\b:|assistant,|ai reviewer|disregard|do not draft|output disposition", re.IGNORECASE)


def inr(amount: float) -> str:
    """``1234567.5`` -> ``₹12,34,567``."""
    whole = int(round(abs(amount)))
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{'-' if amount < 0 else ''}₹{s}"


def ist(value: str | datetime) -> str:
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    return (dt + IST).strftime("%d %b %Y")


def cite(*ids: str | None) -> str:
    """``[EVD-000001][EVD-000002]`` for the non-empty ids."""
    return "".join(f"[{i}]" for i in ids if i)


def clean_remark(text: str | None) -> str:
    """Strip control characters and truncate (remarks are attacker-controlled)."""
    return _CONTROL.sub(" ", text or "")[:REMARK_MAX]


def untrusted(remarks: list[str]) -> str:
    """Wrap remarks for a prompt; the system prompt says this block is data only."""
    body = "\n".join(f"- {clean_remark(r)}" for r in remarks)
    return f"<untrusted_data>\n{body}\n</untrusted_data>"


def looks_like_instruction(text: str | None) -> bool:
    return bool(_INJECTION.search(text or ""))
