"""Text helpers shared by the agents: INR with Indian grouping, IST dates,
citation tags and untrusted-data handling for transaction remarks.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

IST = timedelta(hours=5, minutes=30)
REMARK_MAX = 140
REASON_MAX = 1500
REASON_SEPARATOR = "; "
_EVD_REF = re.compile(r"\[?(?P<id>EVD-\d{6})\]?")
_SPACE_RUN = re.compile(r"[ \t]{2,}")
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
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


def fallback_reason(exc: Exception) -> str:
    """Short, visible reason a node used its template.

    Joins the ``provider/model: cause`` strings the LLM client collected in
    ``exc.detail["errors"]``; falls back to the exception message when there
    are none. The strings hold no keys or prompts. Trimmed to 1500 characters, enough for a Groq error
    code and a short ``failed_generation`` excerpt.
    """
    detail = getattr(exc, "detail", None)
    errors = detail.get("errors") if isinstance(detail, dict) else None
    joined = REASON_SEPARATOR.join(str(e) for e in errors) if errors else ""
    message = getattr(exc, "message", None) or str(exc) or type(exc).__name__
    return (joined or message)[:REASON_MAX]


def strip_unknown_ids(text: str | None, valid: set[str] | frozenset[str]) -> str:
    """Remove every ``EVD-nnnnnn`` (bracketed or bare) that is not in ``valid``.

    Why: a sentence can carry an id from an older run or one the model made up;
    the critic would flag it, so it is dropped before the report is built.

    Args:
        text: Narrative text, may be None.
        valid: Evidence ids of the current ledger.

    Returns:
        Text without unknown ids and with doubled spaces collapsed.
    """
    if not text:
        return text or ""

    def keep(match: re.Match[str]) -> str:
        return match.group(0) if match.group("id") in valid else ""

    out = _EVD_REF.sub(keep, text)
    if out == text:
        return text
    return _TRAILING_SPACE.sub("", _SPACE_RUN.sub(" ", out)).replace(" .", ".").replace(" ,", ",")


def looks_like_instruction(text: str | None) -> bool:
    return bool(_INJECTION.search(text or ""))
