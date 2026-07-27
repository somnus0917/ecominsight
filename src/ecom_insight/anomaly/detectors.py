from __future__ import annotations

import math
from abc import ABC, abstractmethod
from statistics import fmean, median, pstdev

import numpy as np
from sklearn.ensemble import IsolationForest

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
        relative_threshold: float = 0.25,
    ) -> None:
        self.window = window
        self.minimum_history = window
        self.relative_threshold = relative_threshold

    def detect(self, series: MetricSeries) -> list[DetectionPoint]:
        results: list[DetectionPoint] = []
        for index in range(self.minimum_history, len(series.points)):
            history = [point.value for point in series.points[index - self.window : index]]
            baseline = median(history)
            current = series.points[index]
            change = _change_rate(current.value, baseline)
            score = abs(change) if change is not None else 0.0
            results.append(
                DetectionPoint(
                    date=current.date,
                    current_value=current.value,
                    baseline_value=baseline,
                    change_rate=change,
                    anomaly_score=score,
                    is_anomaly=score >= self.relative_threshold,
                    history_size=len(history),
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


def default_detectors() -> tuple[BaseDetector, ...]:
    return (
        FixedThresholdDetector(),
        RollingZScoreDetector(),
        RollingMADDetector(),
        IsolationForestDetector(),
    )
