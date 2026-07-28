from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ecom_insight.privacy import PrivacySanitizer


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    database_exists: bool
    feedback_store_ready: bool
    data_updated_at: date | None
    data_mode: Literal["real", "demo"] = "demo"


class KpiValue(ApiModel):
    code: str
    label: str
    value: float
    unit: str


class TrendPoint(ApiModel):
    date: date
    paid_amount: float
    paid_orders: int
    refund_amount: float
    ad_spend: float
    settlement_amount: float


class OverviewResponse(ApiModel):
    data_updated_at: date | None
    kpis: list[KpiValue]
    trend: list[TrendPoint]
    shops: list[dict[str, Any]]


class PaginatedResponse(ApiModel):
    items: list[dict[str, Any]]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


FeedbackDecision = Literal["accepted", "rejected", "corrected"]


class FeedbackCreate(ApiModel):
    decision: FeedbackDecision
    corrected_cause_code: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)
    reviewer_alias: str | None = Field(default=None, max_length=80)

    @field_validator("notes", "reviewer_alias")
    @classmethod
    def reject_sensitive_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        matches = PrivacySanitizer.sensitive_matches(value)
        if matches:
            raise ValueError(
                f"Feedback contains prohibited sensitive pattern(s): {matches}"
            )
        return value.strip() or None


class FeedbackRecord(ApiModel):
    feedback_id: str
    attribution_id: str
    decision: FeedbackDecision
    corrected_cause_code: str | None
    notes: str | None
    reviewer_alias: str | None
    created_at: datetime

