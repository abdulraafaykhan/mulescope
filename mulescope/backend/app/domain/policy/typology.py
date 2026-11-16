"""Typology labels from the signals that fired (YAML map in ``scoring.yaml``)."""

from __future__ import annotations

from pydantic import BaseModel

from backend.app.domain.policy.config import ScoringConfig


class Typology(BaseModel):
    """A typology label with its plain-language description."""

    label: str
    description: str


def typologies(fired: list[str], cfg: ScoringConfig) -> list[Typology]:
    """Labels whose required signals all fired, in config order."""
    present = set(fired)
    return [Typology(label=name, description=t.description) for name, t in cfg.typologies.items() if set(t.requires_all) <= present]
