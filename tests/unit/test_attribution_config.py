from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ecom_insight.attribution import AttributionRulesConfig


def test_shipped_attribution_rule_config_is_valid() -> None:
    config = AttributionRulesConfig.load(Path("configs/attribution_rules.yaml"))

    assert config.thresholds.decline_rate == 0.15
    assert config.evidence_score.contradiction_penalty_cap == 0.60
    assert len(config.rules) == 10


def test_attribution_threshold_rejects_signed_or_out_of_range_value() -> None:
    with pytest.raises(ValidationError):
        AttributionRulesConfig.model_validate({"thresholds": {"decline_rate": -0.15}})
