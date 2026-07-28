from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DetectorName = Literal["fixed_threshold", "rolling_zscore", "rolling_mad", "isolation_forest"]


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FixedThresholdConfig(_ConfigModel):
    window: int = Field(default=14, ge=2)


class MetricFixedThresholdConfig(_ConfigModel):
    relative_decline: float | None = Field(default=None, gt=0, le=1)
    relative_increase: float | None = Field(default=None, gt=0)
    percentage_point_decline: float | None = Field(default=None, gt=0, le=1)
    percentage_point_increase: float | None = Field(default=None, gt=0, le=1)
    absolute_high: float | None = None
    absolute_low: float | None = None

    @model_validator(mode="after")
    def has_threshold(self) -> MetricFixedThresholdConfig:
        if all(value is None for value in self.__dict__.values()):
            raise ValueError("fixed_threshold requires at least one threshold")
        return self


class RollingScoreConfig(_ConfigModel):
    window: int = Field(default=14, ge=2)
    z_threshold: float = Field(default=3.0, gt=0)
    minimum_scale: float = Field(default=1e-9, gt=0)


class IsolationForestConfig(_ConfigModel):
    window: int = Field(default=42, ge=2)
    minimum_history: int = Field(default=28, ge=2)
    contamination: float = Field(default=0.05, gt=0, lt=0.5)
    random_state: int = 20260727
    estimators: int = Field(default=100, ge=1)

    @model_validator(mode="after")
    def validate_history_window(self) -> IsolationForestConfig:
        if self.minimum_history > self.window:
            raise ValueError("minimum_history cannot exceed window")
        return self


class MetricAnomalyConfig(_ConfigModel):
    enabled: bool = True
    enabled_detectors: tuple[DetectorName, ...]
    fixed_threshold: MetricFixedThresholdConfig | None = None
    minimum_history: int = Field(default=14, ge=2)

    @model_validator(mode="after")
    def validate_detectors(self) -> MetricAnomalyConfig:
        if self.enabled and not self.enabled_detectors:
            raise ValueError("enabled metric requires at least one detector")
        if "fixed_threshold" in self.enabled_detectors and self.fixed_threshold is None:
            raise ValueError("fixed_threshold detector requires metric fixed_threshold settings")
        return self


class DetectorRegistryConfig(_ConfigModel):
    fixed_threshold: FixedThresholdConfig = Field(default_factory=FixedThresholdConfig)
    rolling_zscore: RollingScoreConfig = Field(default_factory=RollingScoreConfig)
    rolling_mad: RollingScoreConfig = Field(
        default_factory=lambda: RollingScoreConfig(z_threshold=3.5)
    )
    isolation_forest: IsolationForestConfig = Field(default_factory=IsolationForestConfig)


class AggregationConfig(_ConfigModel):
    policy: Literal["any", "consensus", "weighted"] = "any"
    detector_weights: dict[DetectorName, float] = Field(default_factory=dict)
    consensus_min_detectors: int = Field(default=2, ge=1)
    weighted_trigger_threshold: float = Field(default=1.0, gt=0)


class RecoveryConfig(_ConfigModel):
    enabled: bool = True
    resolved_after_normal_points: int = Field(default=2, ge=1)
    maximum_gap_days: int = Field(default=3, ge=1)
    direction_reversal_required: bool = False


class AnomalyConfig(_ConfigModel):
    schema_version: str = "2"
    detectors: DetectorRegistryConfig = Field(default_factory=DetectorRegistryConfig)
    metrics: dict[str, MetricAnomalyConfig] = Field(default_factory=dict)
    aggregation: AggregationConfig = Field(default_factory=AggregationConfig)
    recovery: RecoveryConfig = Field(default_factory=RecoveryConfig)

    @model_validator(mode="before")
    @classmethod
    def migrate_v1_shape(cls, value: object) -> object:
        """Read the retired v1 file shape so local users get a safe upgrade path."""
        if not isinstance(value, dict) or "detectors" in value:
            return value
        legacy_names = ("fixed_threshold", "rolling_zscore", "rolling_mad", "isolation_forest")
        if not set(legacy_names).intersection(value):
            return value
        payload = dict(value)
        fixed = dict(payload.pop("fixed_threshold", {}))
        threshold = fixed.pop("relative_threshold", 0.25)
        detectors = {"fixed_threshold": fixed}
        for name in legacy_names[1:]:
            if name in payload:
                detectors[name] = payload.pop(name)
        payload["detectors"] = detectors
        payload["metrics"] = {
            "__legacy__": {
                "enabled_detectors": list(legacy_names),
                "fixed_threshold": {
                    "relative_decline": threshold,
                    "relative_increase": threshold,
                },
            }
        }
        return payload

    @classmethod
    def load(cls, path: Path) -> AnomalyConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Anomaly config must contain a YAML mapping: {path}")
        return cls.model_validate(payload)
