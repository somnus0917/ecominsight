from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ecom_insight.attribution import (
    AttributionCandidate,
    EvidenceItem,
    MetricDecomposition,
)
from ecom_insight.retrieval import RetrievalHit


class ReportingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceBundle(ReportingModel):
    attribution_id: str
    entity_type: str
    entity_id: str
    date: date
    target_metric: str
    detector_names: list[str]
    anomaly_score: float = Field(ge=0)
    severity: Literal["low", "medium", "high"]
    decomposition: MetricDecomposition | None
    candidates: list[AttributionCandidate]
    evidence: list[EvidenceItem]
    missing_information: list[str]
    retrieved_documents: list[RetrievalHit]
    data_origin: Literal["real", "demo"]


class ReportFact(ReportingModel):
    fact: str
    evidence_ids: list[str] = Field(min_length=1)
    source: str
    confidence: float = Field(ge=0, le=1)
    status: Literal["confirmed_fact"] = "confirmed_fact"


ReportCauseStatus = Literal[
    "supported_inference",
    "unverified_hypothesis",
    "insufficient_data",
]


class ReportCause(ReportingModel):
    cause: str
    evidence_ids: list[str]
    historical_document_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    status: ReportCauseStatus


class ReportDocumentReference(ReportingModel):
    document_id: str
    document_type: str
    title: str
    score: float


class AttributionReport(ReportingModel):
    report_id: str
    attribution_id: str
    summary: str
    summary_evidence_ids: list[str] = Field(min_length=1)
    confirmed_facts: list[ReportFact]
    possible_causes: list[ReportCause]
    missing_information: list[str]
    recommended_checks: list[str]
    retrieved_documents: list[ReportDocumentReference]
    generator: str


class ReportValidation(ReportingModel):
    valid: bool
    claim_count: int
    unsupported_claim_count: int
    invalid_evidence_ids: list[str]
    invalid_document_ids: list[str]
    prohibited_causal_phrases: list[str]
    errors: list[str]
