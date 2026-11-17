"""Signal registry (open/closed: add a signal by registering a function).

A signal function takes the metrics and its rule from ``scoring.yaml`` and
returns a :class:`SignalHit` with the points it contributes (0 when it does
not fire) and a plain-language reason. Risk signals add points, mitigators
subtract them. Used by ``domain/policy/scoring.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from backend.app.domain.metrics import FlowMetrics
from backend.app.domain.policy.config import SignalRule


class SignalHit(BaseModel):
    """Result of evaluating one signal."""

    name: str
    kind: str  # "risk" | "mitigator"
    fired: bool
    points: float
    reason: str
    metric_keys: list[str]


SignalFn = Callable[[FlowMetrics, SignalRule], SignalHit]


@dataclass(frozen=True)
class RegisteredSignal:
    name: str
    kind: str
    fn: SignalFn


_SIGNALS: dict[str, RegisteredSignal] = {}


def register_signal(name: str, kind: str = "risk") -> Callable[[SignalFn], SignalFn]:
    """Register ``fn`` as signal ``name`` (``kind`` is ``risk`` or ``mitigator``)."""

    def deco(fn: SignalFn) -> SignalFn:
        _SIGNALS[name] = RegisteredSignal(name, kind, fn)
        return fn

    return deco


def registered(kind: str) -> list[RegisteredSignal]:
    """Registered signals of one kind, in registration order."""
    return [s for s in _SIGNALS.values() if s.kind == kind]


def hit(name: str, kind: str, fired: bool, points: float, reason: str, keys: list[str]) -> SignalHit:
    return SignalHit(name=name, kind=kind, fired=fired, points=points if fired else 0.0, reason=reason, metric_keys=keys)
