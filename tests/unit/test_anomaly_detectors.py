from __future__ import annotations

from datetime import date, timedelta

import pytest

from ecom_insight.anomaly import (
    AnomalyConfig,
    FixedThresholdDetector,
    IsolationForestDetector,
    MetricSeries,
    RollingMADDetector,
    RollingZScoreDetector,
    TimeSeriesPoint,
)
from ecom_insight.anomaly.detectors import default_detectors


def _series(*, anomaly_index: int = 35, anomaly_value: float = 40.0) -> MetricSeries:
    start = date(2025, 1, 1)
    values = [100.0 + ((index % 7) - 3) * 0.4 for index in range(60)]
    values[anomaly_index] = anomaly_value
    return MetricSeries(
        entity_type="shop",
        entity_id="Shop_A",
        metric="paid_amount",
        points=tuple(
            TimeSeriesPoint(date=start + timedelta(days=index), value=value)
            for index, value in enumerate(values)
        ),
    )


@pytest.mark.parametrize(
    "detector",
    [
        FixedThresholdDetector(),
        RollingZScoreDetector(),
        RollingMADDetector(),
        IsolationForestDetector(estimators=30),
    ],
)
def test_detectors_find_large_controlled_drop(detector: object) -> None:
    results = detector.detect(_series())  # type: ignore[attr-defined]
    detected_dates = {result.date for result in results if result.is_anomaly}
    assert date(2025, 2, 5) in detected_dates


def test_rolling_baseline_excludes_current_point() -> None:
    target = date(2025, 2, 5)
    result = next(point for point in RollingMADDetector().detect(_series()) if point.date == target)
    assert result.baseline_value > 99
    assert result.current_value == 40
    assert result.change_rate is not None and result.change_rate < -0.5


def test_metric_series_rejects_duplicate_dates() -> None:
    point = TimeSeriesPoint(date=date(2025, 1, 1), value=1.0)
    with pytest.raises(ValueError, match="unique"):
        MetricSeries(
            entity_type="shop",
            entity_id="Shop_A",
            metric="paid_amount",
            points=(point, point),
        )


def test_isolation_forest_does_not_flag_constant_series() -> None:
    start = date(2025, 1, 1)
    series = MetricSeries(
        entity_type="shop",
        entity_id="Shop_A",
        metric="commission_rate",
        points=tuple(
            TimeSeriesPoint(date=start + timedelta(days=index), value=0.04) for index in range(60)
        ),
    )
    results = IsolationForestDetector(estimators=30).detect(series)
    assert not any(result.is_anomaly for result in results)


def test_default_detectors_use_versioned_config() -> None:
    config = AnomalyConfig.model_validate(
        {
            "fixed_threshold": {"window": 9, "relative_threshold": 0.4},
            "rolling_zscore": {"window": 10, "z_threshold": 2.5},
            "rolling_mad": {"window": 11, "z_threshold": 3.2},
            "isolation_forest": {
                "window": 20,
                "minimum_history": 15,
                "contamination": 0.1,
                "estimators": 12,
            },
        }
    )

    fixed, zscore, mad, forest = default_detectors(config)

    assert fixed.minimum_history == 9
    assert zscore.minimum_history == 10
    assert mad.minimum_history == 11
    assert forest.minimum_history == 15
