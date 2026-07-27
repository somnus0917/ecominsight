from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ScenarioType = Literal[
    "traffic_drop",
    "click_rate_drop",
    "conversion_drop",
    "aov_drop",
    "refund_spike",
    "overstock",
    "ad_waste",
    "stockout",
    "commission_spike",
    "settlement_drop",
]
Direction = Literal["increase", "decrease"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoShop(StrictModel):
    shop_id: str = Field(pattern=r"^Shop_[A-Z]$")
    platform: str
    volume_factor: float = Field(gt=0)


class DemoScenario(StrictModel):
    scenario_id: str = Field(pattern=r"^SYN_[A-Z0-9_]+$")
    scenario_type: ScenarioType
    shop_id: str
    start_day: int = Field(ge=14)
    duration_days: int = Field(ge=1)
    magnitude: float = Field(gt=0)
    target_metric: str
    expected_direction: Direction
    expected_evidence: list[str] = Field(min_length=2)
    target_product_index: int | None = Field(default=None, ge=0)


class DemoConfig(StrictModel):
    schema_version: str
    dataset_version: str
    synthetic: Literal[True]
    seed: int
    start_date: date
    days: int = Field(ge=56)
    products_per_shop: int = Field(ge=3, le=6)
    search_terms_per_shop: int = Field(ge=2, le=4)
    shops: list[DemoShop] = Field(min_length=2)
    scenarios: list[DemoScenario] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> DemoConfig:
        shop_ids = [shop.shop_id for shop in self.shops]
        if len(shop_ids) != len(set(shop_ids)):
            raise ValueError("shop_id values must be unique")
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario_id values must be unique")
        for scenario in self.scenarios:
            if scenario.shop_id not in shop_ids:
                raise ValueError(f"Unknown scenario shop_id: {scenario.shop_id}")
            if scenario.start_day + scenario.duration_days > self.days:
                raise ValueError(f"Scenario exceeds configured date range: {scenario.scenario_id}")
            if (
                scenario.target_product_index is not None
                and scenario.target_product_index >= self.products_per_shop
            ):
                raise ValueError(f"Scenario product index is out of range: {scenario.scenario_id}")
        return self

    @classmethod
    def load(cls, path: Path) -> DemoConfig:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Demo config must contain a YAML mapping: {path}")
        return cls.model_validate(payload)


class ScenarioVerification(StrictModel):
    scenario_id: str
    target_metric: str
    baseline_value: float
    scenario_value: float
    change_rate: float | None
    expected_direction: Direction
    passed: bool
    supporting_metrics: dict[str, float | int | str | bool | None]
