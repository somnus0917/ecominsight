from __future__ import annotations

import math
from abc import ABC, abstractmethod
from statistics import fmean, median, pstdev

import numpy as np
from sklearn.ensemble import IsolationForest

from ecom_insight.anomaly.config import AnomalyConfig, MetricFixedThresholdConfig
from ecom_insight.anomaly.models import DetectionPoint, MetricSeries


def _change_rate(current: float, baseline: float) -> float | None:
    return (current - baseline) / abs(baseline) if baseline else None


class BaseDetector(ABC):
    name: str
    minimum_history: int

    @abstractmethod
    def detect(self, series: MetricSeries) -> list[DetectionPoint]:
        """Return scored points after the detector's history gate."""


class FixedThresholdDetector(BaseDetector):
    name = "fixed_threshold"

    def __init__(
        self,
        *,
        window: int = 14,
        thresholds: MetricFixedThresholdConfig | None = None,
        relative_threshold: float | None = None,
    ) -> None:
        self.window = window
        self.minimum_history = window
        self.thresholds = thresholds or MetricFixedThresholdConfig(
            relative_decline=relative_threshold or 0.25,
            relative_increase=relative_threshold or 0.25,
        )

    def detect(self, series: MetricSeries) -> list[DetectionPoint]:
        results: list[DetectionPoint] = []
        for index in range(self.minimum_history, len(series.points)):
            history = [point.value for point in series.points[index - self.window : index]]
            baseline = median(history)
            current = series.points[index]
            change = _change_rate(current.value, baseline)
            triggered: tuple[str, float] | None = None
            tests = (
                (
                    "relative_decline",
                    change is not None
                    and change <= -float(self.thresholds.relative_decline or float("inf")),
                    self.thresholds.relative_decline,
                ),
                (
                    "relative_increase",
                    change is not None
                    and change >= float(self.thresholds.relative_increase or float("inf")),
                    self.thresholds.relative_increase,
                ),
                (
                    "percentage_point_decline",
                    current.value - baseline
                    <= -float(self.thresholds.percentage_point_decline or float("inf")),
                    self.thresholds.percentage_point_decline,
                ),
                (
                    "percentage_point_increase",
                    current.value - baseline
                    >= float(self.thresholds.percentage_point_increase or float("inf")),
                    self.thresholds.percentage_point_increase,
                ),
                (
                    "absolute_high",
                    self.thresholds.absolute_high is not None
                    and current.value >= self.thresholds.absolute_high,
                    self.thresholds.absolute_high,
                ),
                (
                    "absolute_low",
                    self.thresholds.absolute_low is not None
                    and current.value <= self.thresholds.absolute_low,
                    self.thresholds.absolute_low,
                ),
            )
            for name, passed, threshold in tests:
                if passed and threshold is not None:
                    triggered = (name, float(threshold))
                    break
            score = abs(change) if change is not None else abs(current.value - baseline)
            results.append(
                DetectionPoint(
                    date=current.date,
                    current_value=current.value,
                    baseline_value=baseline,
                    change_rate=change,
                    anomaly_score=score,
                    is_anomaly=triggered is not None,
                    history_size=len(history),
                    trigger_type=triggered[0] if triggered else None,
                    trigger_threshold=triggered[1] if triggered else None,
                )
            )
        return results


class RollingZScoreDetector(BaseDetector):
    name = "rolling_zscore"

    def __init__(
        self,
        *,
        window: int = 14,
        z_threshold: float = 3.0,
        minimum_scale: float = 1e-9,
    ) -> None:
        self.window = window
        self.minimum_history = window
        self.z_threshold = z_threshold
        self.minimum_scale = minimum_scale

    def detect(self, series: MetricSeries) -> list[DetectionPoint]:
        results: list[DetectionPoint] = []
        for index in range(self.minimum_history, len(series.points)):
            history = [point.value for point in series.points[index - self.window : index]]
            baseline = fmean(history)
            scale = pstdev(history)
            current = series.points[index]
            score = abs(current.value - baseline) / scale if scale > self.minimum_scale else 0.0
            results.append(
                DetectionPoint(
                    date=current.date,
                    current_value=current.value,
                    baseline_value=baseline,
                    change_rate=_change_rate(current.value, baseline),
                    anomaly_score=score,
                    is_anomaly=score >= self.z_threshold,
                    history_size=len(history),
                )
            )
        return results


class RollingMADDetector(BaseDetector):
    name = "rolling_mad"

    def __init__(
        self,
        *,
        window: int = 14,
        z_threshold: float = 3.5,
        minimum_scale: float = 1e-9,
    ) -> None:
        self.window = window
        self.minimum_history = window
        self.z_threshold = z_threshold
        self.minimum_scale = minimum_scale

    def detect(self, series: MetricSeries) -> list[DetectionPoint]:
        results: list[DetectionPoint] = []
        for index in range(self.minimum_history, len(series.points)):
            history = [point.value for point in series.points[index - self.window : index]]
            baseline = median(history)
            mad = median([abs(value - baseline) for value in history])
            current = series.points[index]
            score = (
                0.6745 * abs(current.value - baseline) / mad if mad > self.minimum_scale else 0.0
            )
            results.append(
                DetectionPoint(
                    date=current.date,
                    current_value=current.value,
                    baseline_value=baseline,
                    change_rate=_change_rate(current.value, baseline),
                    anomaly_score=score,
                    is_anomaly=score >= self.z_threshold,
                    history_size=len(history),
                )
            )
        return results


class IsolationForestDetector(BaseDetector):
    name = "isolation_forest"

    def __init__(
        self,
        *,
        window: int = 42,
        minimum_history: int = 28,
        contamination: float = 0.05,
        random_state: int = 20260727,
        estimators: int = 100,
    ) -> None:
        if minimum_history > window:
            raise ValueError("minimum_history cannot exceed window")
        self.window = window
        self.minimum_history = minimum_history
        self.contamination = contamination
        self.random_state = random_state
        self.estimators = estimators

    @staticmethod
    def _feature(values: list[float], index: int) -> tuple[float, float]:
        current = values[index]
        previous = values[index - 1] if index > 0 else current
        relative_change = (
            (current - previous) / abs(previous) if not math.isclose(previous, 0.0) else 0.0
        )
        return current, relative_change

    def detect(self, series: MetricSeries) -> list[DetectionPoint]:
        values = [point.value for point in series.points]
        results: list[DetectionPoint] = []
        for index in range(self.minimum_history, len(values)):
            history_start = max(1, index - self.window)
            history_features = np.asarray(
                [
                    self._feature(values, history_index)
                    for history_index in range(history_start, index)
                ],
                dtype=float,
            )
            if len(history_features) < self.minimum_history - 1:
                continue
            current_feature = np.asarray([self._feature(values, index)], dtype=float)
            model = IsolationForest(
                n_estimators=self.estimators,
                contamination=self.contamination,
                random_state=self.random_state,
                n_jobs=1,
            )
            model.fit(history_features)
            decision = float(model.decision_function(current_feature)[0])
            score = -float(model.score_samples(current_feature)[0])
            historical_min = history_features.min(axis=0)
            historical_max = history_features.max(axis=0)
            outside_observed_range = bool(
                np.any(current_feature[0] < historical_min - 1e-12)
                or np.any(current_feature[0] > historical_max + 1e-12)
            )
            is_boundary_novelty = (
                math.isclose(decision, 0.0, abs_tol=1e-12) and outside_observed_range
            )
            baseline = median(values[history_start:index])
            current = series.points[index]
            results.append(
                DetectionPoint(
                    date=current.date,
                    current_value=current.value,
                    baseline_value=baseline,
                    change_rate=_change_rate(current.value, baseline),
                    anomaly_score=max(0.0, score),
                    is_anomaly=decision < -1e-12 or is_boundary_novelty,
                    history_size=len(history_features),
                )
            )
        return results


def build_detectors_for_metric(metric_code: str, config: AnomalyConfig) -> tuple[BaseDetector, ...]:
    metric = config.metrics.get(metric_code)
    if metric is None or not metric.enabled:
        return ()
    active = config.detectors
    built: list[BaseDetector] = []
    for name in metric.enabled_detectors:
        if name == "fixed_threshold":
            assert metric.fixed_threshold is not None
            built.append(
                FixedThresholdDetector(
                    window=active.fixed_threshold.window, thresholds=metric.fixed_threshold
                )
            )
        elif name == "rolling_zscore":
            built.append(
                RollingZScoreDetector(
                    window=active.rolling_zscore.window,
                    z_threshold=active.rolling_zscore.z_threshold,
                    minimum_scale=active.rolling_zscore.minimum_scale,
                )
            )
        elif name == "rolling_mad":
            built.append(
                RollingMADDetector(
                    window=active.rolling_mad.window,
                    z_threshold=active.rolling_mad.z_threshold,
                    minimum_scale=active.rolling_mad.minimum_scale,
                )
            )
        else:
            built.append(
                IsolationForestDetector(
                    window=active.isolation_forest.window,
                    minimum_history=max(
                        metric.minimum_history, active.isolation_forest.minimum_history
                    ),
                    contamination=active.isolation_forest.contamination,
                    random_state=active.isolation_forest.random_state,
                    estimators=active.isolation_forest.estimators,
                )
            )
    return tuple(built)


def default_detectors(config: AnomalyConfig | None = None) -> tuple[BaseDetector, ...]:
    """Compatibility helper; new runners build detectors separately per metric."""
    active = config or AnomalyConfig()
    if active.metrics:
        return build_detectors_for_metric(next(iter(active.metrics)), active)
    return (
        FixedThresholdDetector(
            window=14,
            thresholds=MetricFixedThresholdConfig(relative_decline=0.25, relative_increase=0.25),
        ),
        RollingZScoreDetector(
            window=active.detectors.rolling_zscore.window,
            z_threshold=active.detectors.rolling_zscore.z_threshold,
            minimum_scale=active.detectors.rolling_zscore.minimum_scale,
        ),
        RollingMADDetector(
            window=active.detectors.rolling_mad.window,
            z_threshold=active.detectors.rolling_mad.z_threshold,
            minimum_scale=active.detectors.rolling_mad.minimum_scale,
        ),
        IsolationForestDetector(
            window=active.detectors.isolation_forest.window,
            minimum_history=active.detectors.isolation_forest.minimum_history,
            contamination=active.detectors.isolation_forest.contamination,
            random_state=active.detectors.isolation_forest.random_state,
            estimators=active.detectors.isolation_forest.estimators,
        ),
    )
