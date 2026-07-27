from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

import duckdb
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricRole = Literal["outcome", "driver", "guardrail", "diagnostic"]


class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    role: MetricRole
    definition: str
    formula: str
    source: str
    grain: str
    unit: str
    aggregation: str
    applicable_platforms: list[str]
    null_policy: str
    minimum_history: int = Field(ge=1)
    caveats: list[str]

    @model_validator(mode="after")
    def formula_is_declarative(self) -> MetricDefinition:
        lowered = self.formula.casefold()
        forbidden = (";", "--", "/*", " drop ", " delete ", " update ", " insert ")
        if any(token in f" {lowered} " for token in forbidden):
            raise ValueError(f"Metric formula is not declarative: {self.code}")
        return self


class MetricFramework(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_kpis: list[str]
    drivers: list[str]
    guardrails: list[str]


class MetricRegistryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    canonical_currency: str
    canonical_money_unit: str
    framework: MetricFramework
    metrics: list[MetricDefinition]

    @model_validator(mode="after")
    def metric_codes_are_unique_and_framework_is_valid(self) -> MetricRegistryConfig:
        counts = Counter(metric.code for metric in self.metrics)
        duplicates = sorted(code for code, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"Duplicate metric codes: {duplicates}")

        by_code = {metric.code: metric for metric in self.metrics}
        framework_codes = {
            *self.framework.primary_kpis,
            *self.framework.drivers,
            *self.framework.guardrails,
        }
        missing = sorted(framework_codes - by_code.keys())
        if missing:
            raise ValueError(f"Framework references undefined metrics: {missing}")
        for code in self.framework.primary_kpis:
            if by_code[code].role != "outcome":
                raise ValueError(f"Primary KPI must have outcome role: {code}")
        for code in self.framework.drivers:
            if by_code[code].role != "driver":
                raise ValueError(f"Framework driver must have driver role: {code}")
        for code in self.framework.guardrails:
            if by_code[code].role != "guardrail":
                raise ValueError(f"Framework guardrail must have guardrail role: {code}")
        return self


class MetricRegistry:
    def __init__(self, config: MetricRegistryConfig) -> None:
        self.config = config
        self._by_code = {metric.code: metric for metric in config.metrics}

    @classmethod
    def load(cls, path: Path) -> MetricRegistry:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
        return cls(MetricRegistryConfig.model_validate(payload))

    def get(self, code: str) -> MetricDefinition:
        try:
            return self._by_code[code]
        except KeyError as error:
            raise KeyError(f"Unknown metric code: {code}") from error

    def by_role(self, role: MetricRole) -> list[MetricDefinition]:
        return [metric for metric in self.config.metrics if metric.role == role]

    def publish_to_duckdb(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE metric_registry (
                metric_code VARCHAR PRIMARY KEY,
                metric_name VARCHAR NOT NULL,
                metric_role VARCHAR NOT NULL,
                business_definition VARCHAR NOT NULL,
                formula VARCHAR NOT NULL,
                source VARCHAR NOT NULL,
                grain VARCHAR NOT NULL,
                unit VARCHAR NOT NULL,
                aggregation VARCHAR NOT NULL,
                applicable_platforms VARCHAR[] NOT NULL,
                null_policy VARCHAR NOT NULL,
                minimum_history INTEGER NOT NULL,
                caveats VARCHAR[] NOT NULL,
                registry_version INTEGER NOT NULL
            )
            """
        )
        rows = [
            (
                metric.code,
                metric.name,
                metric.role,
                metric.definition,
                metric.formula,
                metric.source,
                metric.grain,
                metric.unit,
                metric.aggregation,
                metric.applicable_platforms,
                metric.null_policy,
                metric.minimum_history,
                metric.caveats,
                self.config.version,
            )
            for metric in self.config.metrics
        ]
        connection.executemany(
            "INSERT INTO metric_registry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
