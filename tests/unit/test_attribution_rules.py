from __future__ import annotations

from ecom_insight.attribution import AttributionRulesConfig, EvidenceItem
from ecom_insight.attribution.rules import AttributionRuleEngine


def _evidence(metric: str, change_rate: float) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"e-{metric}",
        metric=metric,
        source_table="test_fact",
        current_value=100 * (1 + change_rate),
        baseline_value=100,
        change_rate=change_rate,
        unit="test",
        comparison_window="previous_14_observations_median",
    )


def test_traffic_rule_uses_stable_rates_as_support() -> None:
    candidates = AttributionRuleEngine().evaluate(
        target_metric="paid_amount",
        evidence={
            "paid_amount": _evidence("paid_amount", -0.30),
            "exposure_users": _evidence("exposure_users", -0.28),
            "exposure_click_rate": _evidence("exposure_click_rate", 0.01),
            "click_conversion_rate": _evidence("click_conversion_rate", -0.02),
        },
    )

    traffic = next(candidate for candidate in candidates if candidate.rule_id == "R001")
    assert traffic.status == "supported_inference"
    assert traffic.evidence_score == 1.0
    assert traffic.counter_evidence == []


def test_conversion_rule_preserves_inventory_gap() -> None:
    candidates = AttributionRuleEngine().evaluate(
        target_metric="click_conversion_rate",
        evidence={
            "click_conversion_rate": _evidence("click_conversion_rate", -0.35),
            "paid_amount": _evidence("paid_amount", -0.25),
            "exposure_click_rate": _evidence("exposure_click_rate", 0.02),
        },
    )

    conversion = next(candidate for candidate in candidates if candidate.rule_id == "R003")
    assert conversion.evidence_score == 1.0
    assert "商品-SKU桥接" in conversion.missing_information[0]


def test_rule_engine_does_not_emit_inventory_cause_without_inventory_evidence() -> None:
    candidates = AttributionRuleEngine().evaluate(
        target_metric="click_conversion_rate",
        evidence={
            "click_conversion_rate": _evidence("click_conversion_rate", -0.35),
            "paid_amount": _evidence("paid_amount", -0.25),
        },
    )

    assert all(candidate.rule_id != "R007" for candidate in candidates)


def test_paid_amount_increase_does_not_emit_decline_causes() -> None:
    candidates = AttributionRuleEngine().evaluate(
        target_metric="paid_amount",
        evidence={
            "paid_amount": _evidence("paid_amount", 0.30),
            "exposure_users": _evidence("exposure_users", -0.30),
            "exposure_click_rate": _evidence("exposure_click_rate", -0.30),
            "click_conversion_rate": _evidence("click_conversion_rate", -0.30),
            "avg_order_value": _evidence("avg_order_value", -0.30),
            "refund_rate": _evidence("refund_rate", 0.30),
            "ad_spend": _evidence("ad_spend", 0.30),
            "roas": _evidence("roas", -0.30),
            "available_qty": _evidence("available_qty", -0.80),
            "core_product_paid_amount": _evidence("core_product_paid_amount", -0.30),
        },
    )

    assert candidates == []


def test_rule_thresholds_are_loaded_from_validated_configuration() -> None:
    config = AttributionRulesConfig.model_validate(
        {
            "thresholds": {"decline_rate": 0.40},
            "evidence_score": {},
            "rules": [],
        }
    )
    candidates = AttributionRuleEngine(config).evaluate(
        target_metric="paid_amount",
        evidence={
            "paid_amount": _evidence("paid_amount", -0.30),
            "exposure_users": _evidence("exposure_users", -0.30),
        },
    )

    assert all(candidate.rule_id != "R001" for candidate in candidates)
