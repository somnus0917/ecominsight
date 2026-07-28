"""Validated configuration for deterministic attribution rules."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RuleThresholdConfig(BaseModel):
    """Relative-change thresholds. Values are positive magnitudes, not signed rates."""

    model_config = ConfigDict(extra="forbid")

    decline_rate: float = Field(default=0.15, gt=0, lt=1)
    increase_rate: float = Field(default=0.15, gt=0, lt=1)
    stable_rate: float = Field(default=0.12, ge=0, lt=1)
    refund_rate_increase: float = Field(default=0.20, gt=0, lt=1)
    ad_spend_increase: float = Field(default=0.20, gt=0, lt=1)
    inventory_available_decline: float = Field(default=0.50, gt=0, lt=1)
    commission_rate_increase: float = Field(default=0.20, gt=0, lt=1)
    settlement_ratio_decline: float = Field(default=0.08, gt=0, lt=1)
    days_of_supply_increase: float = Field(default=0.50, gt=0, lt=1)


class EvidenceScoreConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contradiction_penalty_per_item: float = Field(default=0.15, ge=0, le=1)
    contradiction_penalty_cap: float = Field(default=0.60, ge=0, le=1)
    missing_adjustment_source_reliability: float = Field(default=0.85, gt=0, le=1)


class RuleMetadata(BaseModel):
    """Human-readable rule catalogue retained with its executable parameters."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    cause_code: str
    cause: str
    applies_to: list[str]
    preconditions: list[str]
    supporting_evidence: list[str]
    counter_evidence: list[str]
    explanation_template: str


class AttributionRulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    thresholds: RuleThresholdConfig = Field(default_factory=RuleThresholdConfig)
    evidence_score: EvidenceScoreConfig = Field(default_factory=EvidenceScoreConfig)
    rules: list[RuleMetadata] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> AttributionRulesConfig:
        with path.open(encoding="utf-8") as file:
            payload = yaml.safe_load(file)
        return cls.model_validate(payload)
