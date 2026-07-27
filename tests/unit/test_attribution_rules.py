from __future__ import annotations

from ecom_insight.attribution import EvidenceItem
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
    assert traffic.confidence == 1.0
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
    assert conversion.confidence == 1.0
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

