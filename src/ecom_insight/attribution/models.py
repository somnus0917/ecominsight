from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

EvidenceStatus = Literal[
    "confirmed_fact",
    "supported_inference",
    "unverified_hypothesis",
    "insufficient_data",
]
DecompositionMethod = Literal["log_change", "relative_change", "insufficient_data"]


class AttributionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(AttributionModel):
    evidence_id: str
    metric: str
    source_table: str
    current_value: float | None
    baseline_value: float | None
    change_rate: float | None
    unit: str
    comparison_window: str
    status: EvidenceStatus = "confirmed_fact"
    quality_flags: list[str] = Field(default_factory=list)


class FactorContribution(AttributionModel):
    metric: str
    baseline_value: float
    current_value: float
    change_rate: float | None
    log_change: float | None
    contribution_share: float | None


class MetricDecomposition(AttributionModel):
    target_metric: str
    formula: str
    method: DecompositionMethod
    baseline_value: float | None
    current_value: float | None
    target_change_rate: float | None
    target_log_change: float | None
    explained_log_change: float | None
    residual: float | None
    factors: list[FactorContribution] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class EvidenceScoreBreakdown(AttributionModel):
    evidence_completeness: float = Field(ge=0, le=1)
    source_reliability: float = Field(ge=0, le=1)
    directional_consistency: float = Field(ge=0, le=1)
    temporal_alignment: float = Field(ge=0, le=1)
    contradiction_penalty: float = Field(ge=0, le=1)

    @property
    def score(self) -> float:
        raw = (
            self.evidence_completeness
            * self.source_reliability
            * self.directional_consistency
            * self.temporal_alignment
            * (1 - self.contradiction_penalty)
        )
        return round(raw, 6)


class AttributionCandidate(AttributionModel):
    rule_id: str
    cause_code: str
    cause: str
    status: EvidenceStatus
    evidence_score: float = Field(
        ge=0,
        le=1,
        validation_alias=AliasChoices("evidence_score", "confidence"),
    )
    evidence_score_breakdown: EvidenceScoreBreakdown = Field(
        validation_alias=AliasChoices("evidence_score_breakdown", "confidence_breakdown")
    )
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    counter_evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    explanation: str

    @property
    def confidence(self) -> float:
        """Compatibility accessor while persisted consumers migrate to evidence_score."""
        return self.evidence_score

    @property
    def confidence_breakdown(self) -> EvidenceScoreBreakdown:
        """Compatibility accessor for pre-Phase-C readers."""
        return self.evidence_score_breakdown


class AttributionResult(AttributionModel):
    attribution_id: str
    entity_type: str
    entity_id: str
    date: date
    target_metric: str
    detector_names: list[str]
    anomaly_score: float = Field(ge=0)
    severity: Literal["low", "medium", "high"]
    decomposition: MetricDecomposition | None
    candidates: list[AttributionCandidate] = Field(default_factory=list)
    context_evidence: list[EvidenceItem] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    data_origin: Literal["real", "demo"]


# Kept as an import-compatible alias until the persisted warehouse and API are migrated.
ConfidenceBreakdown = EvidenceScoreBreakdown
