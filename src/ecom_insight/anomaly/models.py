from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class TimeSeriesPoint:
    date: date
    value: float


@dataclass(frozen=True, slots=True)
class MetricSeries:
    entity_type: str
    entity_id: str
    metric: str
    points: tuple[TimeSeriesPoint, ...]

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("MetricSeries requires at least one point")
        dates = [point.date for point in self.points]
        if dates != sorted(dates):
            raise ValueError("MetricSeries points must be sorted by date")
        if len(dates) != len(set(dates)):
            raise ValueError("MetricSeries dates must be unique")


@dataclass(frozen=True, slots=True)
class DetectionPoint:
    date: date
    current_value: float
    baseline_value: float
    change_rate: float | None
    anomaly_score: float
    is_anomaly: bool
    history_size: int
    trigger_type: str | None = None
    trigger_threshold: float | None = None


class AnomalyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    entity_id: str
    date: date
    metric: str
    current_value: float
    baseline_value: float
    change_rate: float | None
    anomaly_score: float = Field(ge=0)
    severity: Severity
    detector: str
    evidence: list[dict[str, Any]]
    data_origin: Literal["real", "demo"]


def severity_from_change(change_rate: float | None) -> Severity:
    if change_rate is None:
        return "low"
    magnitude = abs(change_rate)
    if magnitude >= 0.50:
        return "high"
    if magnitude >= 0.30:
        return "medium"
    return "low"
