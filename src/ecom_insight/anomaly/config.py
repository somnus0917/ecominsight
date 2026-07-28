from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FixedThresholdConfig(_ConfigModel):
    window: int = Field(default=14, ge=2)
    relative_threshold: float = Field(default=0.25, gt=0)


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


class AnomalyConfig(_ConfigModel):
    schema_version: str = "1"
    fixed_threshold: FixedThresholdConfig = Field(default_factory=FixedThresholdConfig)
    rolling_zscore: RollingScoreConfig = Field(default_factory=RollingScoreConfig)
    rolling_mad: RollingScoreConfig = Field(
        default_factory=lambda: RollingScoreConfig(z_threshold=3.5)
    )
    isolation_forest: IsolationForestConfig = Field(default_factory=IsolationForestConfig)

    @classmethod
    def load(cls, path: Path) -> AnomalyConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Anomaly config must contain a YAML mapping: {path}")
        return cls.model_validate(payload)
