from __future__ import annotations

import json
from pathlib import Path

from ecom_insight.demo import DemoDataGenerator
from ecom_insight.privacy import PrivacySanitizer

CONFIG_PATH = Path("configs/demo_scenarios.yaml")


def test_demo_generator_produces_verified_cross_domain_data(tmp_path: Path) -> None:
    output_root = tmp_path / "demo"
    result = DemoDataGenerator(
        config_path=CONFIG_PATH,
        output_root=output_root,
        reference_database=None,
    ).generate()

    assert result.all_scenarios_verified
    assert result.scenario_count == 10
    assert result.row_counts["shop_daily"] == 560
    assert result.row_counts["anomaly_labels"] == 10

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["synthetic"] is True
    assert manifest["contains_real_records"] is False
    assert manifest["scenario_verification"] == {"passed": 10, "failed": 0}

    verifications = json.loads(result.verification_path.read_text(encoding="utf-8"))
    assert all(item["passed"] for item in verifications)
    assert {item["scenario_id"] for item in verifications} == set(manifest["scenario_ids"])


def test_demo_generation_is_deterministic_and_privacy_safe(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for output_root in (first_root, second_root):
        DemoDataGenerator(
            config_path=CONFIG_PATH,
            output_root=output_root,
            reference_database=None,
        ).generate()

    first_files = sorted(path.name for path in first_root.glob("*.json"))
    second_files = sorted(path.name for path in second_root.glob("*.json"))
    assert first_files == second_files
    for filename in first_files:
        first_text = (first_root / filename).read_text(encoding="utf-8")
        second_text = (second_root / filename).read_text(encoding="utf-8")
        assert first_text == second_text
        assert PrivacySanitizer.sensitive_matches(first_text) == []


def test_injected_scenarios_have_expected_business_evidence(tmp_path: Path) -> None:
    output_root = tmp_path / "demo"
    result = DemoDataGenerator(
        config_path=CONFIG_PATH,
        output_root=output_root,
        reference_database=None,
    ).generate()
    verifications = {
        item["scenario_id"]: item
        for item in json.loads(result.verification_path.read_text(encoding="utf-8"))
    }

    assert (
        verifications["SYN_TRAFFIC_DROP"]["supporting_metrics"][
            "natural_search_exposure_change_rate"
        ]
        < -0.30
    )
    assert verifications["SYN_AD_WASTE"]["supporting_metrics"]["roas_change_rate"] < -0.30
    assert (
        verifications["SYN_STOCKOUT"]["supporting_metrics"]["core_product_paid_amount_change_rate"]
        < -0.50
    )
    assert (
        verifications["SYN_SETTLEMENT_DROP"]["supporting_metrics"]["paid_amount_change_rate"]
        > -0.10
    )
