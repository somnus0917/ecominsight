from __future__ import annotations

from datetime import date, timedelta

import pytest

from ecom_insight.anomaly import (
    FixedThresholdDetector,
    IsolationForestDetector,
    MetricSeries,
    RollingMADDetector,
    RollingZScoreDetector,
    TimeSeriesPoint,
)


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
