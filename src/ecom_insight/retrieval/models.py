from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal[
    "metric_definition",
    "attribution_rule",
    "historical_case",
    "business_note",
    "analysis_report",
]
DocumentOrigin = Literal["public", "demo", "real_reviewed"]


class RetrievalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeDocument(RetrievalModel):
    document_id: str
    document_type: DocumentType
    title: str
    content: str
    origin: DocumentOrigin
    shop_id: str | None = None
    product_id: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    anomaly_metric: str | None = None
    cause_code: str | None = None
    source_ref: str
    tags: list[str] = Field(default_factory=list)


class RetrievalHit(RetrievalModel):
    document: KnowledgeDocument
    score: float = Field(ge=-1, le=1)
    rank: int = Field(ge=1)


class RetrievalFilters(RetrievalModel):
    document_types: set[DocumentType] | None = None
    shop_id: str | None = None
    anomaly_metric: str | None = None
    cause_code: str | None = None
    exclude_document_ids: set[str] = Field(default_factory=set)

