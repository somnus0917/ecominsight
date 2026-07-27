from __future__ import annotations

import math

import pytest

from ecom_insight.attribution import decompose_paid_amount


def test_paid_amount_log_decomposition_is_exact_for_consistent_funnel() -> None:
    baseline = {
        "paid_amount": 1000.0,
        "exposure_users": 1000.0,
        "exposure_click_rate": 0.10,
        "click_conversion_rate": 0.05,
        "avg_order_value": 200.0,
    }
    current = {
        "paid_amount": 750.0,
        "exposure_users": 750.0,
        "exposure_click_rate": 0.10,
        "click_conversion_rate": 0.05,
        "avg_order_value": 200.0,
    }

    result = decompose_paid_amount(current=current, baseline=baseline)

    assert result.method == "log_change"
    assert result.target_log_change == pytest.approx(math.log(0.75))
    assert result.residual == pytest.approx(0.0)
    traffic = next(item for item in result.factors if item.metric == "exposure_users")
    assert traffic.contribution_share == pytest.approx(1.0)


def test_paid_amount_decomposition_reports_missing_inputs() -> None:
    result = decompose_paid_amount(
        current={"paid_amount": 100.0},
        baseline={"paid_amount": 120.0},
    )

    assert result.method == "insufficient_data"
    assert result.factors == []
    assert "exposure_users" in result.limitations[0]


def test_paid_amount_decomposition_uses_documented_fallback_for_zero() -> None:
    baseline = {
        "paid_amount": 1000.0,
        "exposure_users": 1000.0,
        "exposure_click_rate": 0.10,
        "click_conversion_rate": 0.05,
        "avg_order_value": 200.0,
    }
    current = {
        "paid_amount": 0.0,
        "exposure_users": 0.0,
        "exposure_click_rate": 0.10,
        "click_conversion_rate": 0.05,
        "avg_order_value": 200.0,
    }

    result = decompose_paid_amount(current=current, baseline=baseline)

    assert result.method == "relative_change"
    assert result.target_change_rate == -1.0
    assert result.residual == pytest.approx(0.0)
    assert result.limitations
