"""Typed shapes of ``config/scoring.yaml`` and ``config/playbook.yaml``.

Pure Pydantic models (domain layer): ``core/config_files.py`` loads the YAML
into them, and the detector, scoring, disposition policy and action planner
read thresholds and weights only from these objects.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Cfg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FanInRule(_Cfg):
    min_senders: int
    min_inflow: float
    min_pass_through: float


class HighValueRule(_Cfg):
    min_inflow: float
    min_pass_through: float


class DormantRule(_Cfg):
    min_dormancy_days: int
    min_inflow: float


class DetectorRules(_Cfg):
    fan_in_pass_through: FanInRule
    high_value_pass_through: HighValueRule
    dormant_reactivation: DormantRule


class PriorityBands(_Cfg):
    high_inflow: float
    high_senders: int
    medium_inflow: float


class DetectorConfig(_Cfg):
    rule_version: str
    window_days: int
    rules: DetectorRules
    priority: PriorityBands


class MetricsConfig(_Cfg):
    history_days: int
    exit_match_ratio: float
    pass_through_hours: int
    round_amount: float
    structuring_limits: list[float]
    structuring_margin: float
    cash_like_channels: list[str]
    business_keywords: list[str]
    top_beneficiaries: int


class SignalRule(_Cfg):
    """A risk signal: weight plus named thresholds."""

    weight: float
    thresholds: dict[str, float] = Field(default_factory=dict)
    description: str = ""


class DispositionConfig(_Cfg):
    close_below: float
    str_at: float
    caution_band: float
    str_min_signals: int
    str_required_any: list[str]
    hard_floor_victim_senders: int


class Typology(_Cfg):
    requires_all: list[str]
    description: str


class ScoringConfig(_Cfg):
    """Validated ``config/scoring.yaml``."""

    version: str
    policy_version: str
    detector: DetectorConfig
    metrics: MetricsConfig
    signals: dict[str, SignalRule]
    mitigators: dict[str, SignalRule]
    disposition: DispositionConfig
    typologies: dict[str, Typology]


class ActionSpec(_Cfg):
    """One action the playbook can propose."""

    type: str
    owner_role: str
    due_in_days: int
    requires_approval: bool
    reversible: bool
    mock_tool: str
    params: dict[str, float | str | int] = Field(default_factory=dict)
    description: str = ""


class PlaybookRule(_Cfg):
    """When the trigger matches, propose ``actions``.

    ``disposition`` (optional) must equal the policy result; ``signals_any``
    (optional) needs one fired signal; ``min_score`` and ``min_amount`` are
    optional extra conditions; ``stale_kyc`` matches a stale KYC record.
    """

    name: str
    disposition: str | None = None
    signals_any: list[str] = Field(default_factory=list)
    min_score: float | None = None
    min_amount: float | None = None
    stale_kyc: bool | None = None
    linked_accounts: bool | None = None
    actions: list[str]


class PlaybookConfig(_Cfg):
    """Validated ``config/playbook.yaml``."""

    version: str
    sla_days_by_priority: dict[int, int]
    str_due_days: int
    tipping_off_terms: list[str]
    str_required_sections: list[str]
    required_evidence_kinds: list[str]
    actions: dict[str, ActionSpec]
    rules: list[PlaybookRule]
