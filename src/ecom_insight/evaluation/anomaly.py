from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import fmean
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict

from ecom_insight.anomaly import BaseDetector, MetricSeries, TimeSeriesPoint
from ecom_insight.anomaly.detectors import default_detectors

LOGGER = structlog.get_logger(__name__)


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseEvaluation(EvaluationModel):
    detector: str
    scenario_id: str
    metric: str
    eligible_points: int
    positive_points: int
    predicted_points: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    detected: bool
    detection_delay_days: int | None


class DetectorEvaluation(EvaluationModel):
    detector: str
    eligible_points: int
    positive_points: int
    predicted_points: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    detected_scenarios: int
    scenario_count: int
    scenario_recall: float
    mean_detection_delay_days: float | None


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    scenario_id: str
    series: MetricSeries
    positive_dates: frozenset[date]
    start_date: date


@dataclass(frozen=True, slots=True)
class AnomalyEvaluationResult:
    artifact_path: Path
    predictions_path: Path
    case_count: int
    detector_results: tuple[DetectorEvaluation, ...]


def _safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"Expected a JSON record list: {path}")
    return payload


class DemoBenchmarkLoader:
    def __init__(self, demo_root: Path) -> None:
        self.demo_root = demo_root.resolve()

    def load(self) -> list[BenchmarkCase]:
        labels = _load_json_records(self.demo_root / "anomaly_labels.json")
        source_cache: dict[str, list[dict[str, Any]]] = {}
        cases: list[BenchmarkCase] = []
        for label in labels:
            metric = str(label["target_metric"])
            source_name, date_field = self._source_for_metric(metric)
            rows = source_cache.setdefault(
                source_name,
                _load_json_records(self.demo_root / f"{source_name}.json"),
            )
            filtered = self._filter_rows(rows, label)
            points = tuple(
                TimeSeriesPoint(
                    date=date.fromisoformat(str(row[date_field])),
                    value=float(row[metric]),
                )
                for row in sorted(filtered, key=lambda item: str(item[date_field]))
                if row.get(metric) is not None
            )
            start_date = date.fromisoformat(str(label["start_date"]))
            end_date = date.fromisoformat(str(label["end_date"]))
            positive_dates = frozenset(
                point.date for point in points if start_date <= point.date <= end_date
            )
            if not positive_dates:
                raise ValueError(f"Label has no matching metric rows: {label['scenario_id']}")
            entity_id = str(label["entity_id"])
            target_product_id = label.get("target_product_id")
            if target_product_id:
                entity_id = f"{entity_id}/{target_product_id}"
            cases.append(
                BenchmarkCase(
                    scenario_id=str(label["scenario_id"]),
                    series=MetricSeries(
                        entity_type=str(label["entity_type"]),
                        entity_id=entity_id,
                        metric=metric,
                        points=points,
                    ),
                    positive_dates=positive_dates,
                    start_date=start_date,
                )
            )
        return cases

    @staticmethod
    def _source_for_metric(metric: str) -> tuple[str, str]:
        if metric in {"available_qty", "days_of_supply"}:
            return "inventory_daily", "snapshot_date"
        if metric in {"platform_commission_rate", "settlement_ratio"}:
            return "financial_daily", "date"
        return "shop_daily", "date"

    @staticmethod
    def _filter_rows(rows: list[dict[str, Any]], label: dict[str, Any]) -> list[dict[str, Any]]:
        entity_id = str(label["entity_id"])
        target_product_id = label.get("target_product_id")
        return [
            row
            for row in rows
            if str(row.get("shop_id")) == entity_id
            and (target_product_id is None or str(row.get("product_id")) == str(target_product_id))
        ]


class AnomalyEvaluator:
    def __init__(
        self,
        demo_root: Path,
        artifact_root: Path,
        detectors: tuple[BaseDetector, ...] | None = None,
    ) -> None:
        self.demo_root = demo_root.resolve()
        self.artifact_root = artifact_root.resolve()
        self.detectors = detectors or default_detectors()

    def run(self) -> AnomalyEvaluationResult:
        cases = DemoBenchmarkLoader(self.demo_root).load()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        case_results: list[CaseEvaluation] = []
        prediction_rows: list[dict[str, Any]] = []
        for detector in self.detectors:
            for case in cases:
                result, predictions = self._evaluate_case(detector, case)
                case_results.append(result)
                prediction_rows.extend(predictions)

        detector_results = tuple(
            self._aggregate(detector.name, case_results) for detector in self.detectors
        )
        payload = {
            "schema_version": "1",
            "data_origin": "demo",
            "evaluation_grain": "detector x scenario x eligible date",
            "label_policy": (
                "Only controlled event-window dates are positive. "
                "Scenario identifiers are excluded from detector features."
            ),
            "case_count": len(cases),
            "detectors": [result.model_dump(mode="json") for result in detector_results],
            "cases": [result.model_dump(mode="json") for result in case_results],
            "limitations": [
                "Results measure recovery of controlled scenarios, not production accuracy.",
                "Point-level false positives include recovery effects outside labeled windows.",
                "Detector thresholds are fixed before evaluation and are not tuned on labels.",
                "Real-data alerts remain unlabeled and are reported separately.",
            ],
        }
        artifact_path = self.artifact_root / "anomaly_evaluation.json"
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        predictions_path = self.artifact_root / "anomaly_predictions.json"
        predictions_path.write_text(
            json.dumps(prediction_rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        LOGGER.info(
            "phase4_anomaly_evaluation_complete",
            case_count=len(cases),
            detector_results=[result.model_dump(mode="json") for result in detector_results],
        )
        return AnomalyEvaluationResult(
            artifact_path=artifact_path,
            predictions_path=predictions_path,
            case_count=len(cases),
            detector_results=detector_results,
        )

    @staticmethod
    def _evaluate_case(
        detector: BaseDetector, case: BenchmarkCase
    ) -> tuple[CaseEvaluation, list[dict[str, Any]]]:
        detections = detector.detect(case.series)
        tp = fp = tn = fn = 0
        predicted_positive_dates: list[date] = []
        predictions: list[dict[str, Any]] = []
        for detection in detections:
            actual = detection.date in case.positive_dates
            predicted = detection.is_anomaly
            if actual and predicted:
                tp += 1
                predicted_positive_dates.append(detection.date)
            elif actual:
                fn += 1
            elif predicted:
                fp += 1
            else:
                tn += 1
            predictions.append(
                {
                    "scenario_id": case.scenario_id,
                    "detector": detector.name,
                    "entity_id": case.series.entity_id,
                    "date": detection.date.isoformat(),
                    "metric": case.series.metric,
                    "current_value": detection.current_value,
                    "baseline_value": detection.baseline_value,
                    "change_rate": detection.change_rate,
                    "anomaly_score": detection.anomaly_score,
                    "predicted_anomaly": predicted,
                    "ground_truth_anomaly": actual,
                }
            )
        delay = (
            min(
                (detected_date - case.start_date).days for detected_date in predicted_positive_dates
            )
            if predicted_positive_dates
            else None
        )
        return (
            CaseEvaluation(
                detector=detector.name,
                scenario_id=case.scenario_id,
                metric=case.series.metric,
                eligible_points=len(detections),
                positive_points=tp + fn,
                predicted_points=tp + fp,
                true_positive=tp,
                false_positive=fp,
                true_negative=tn,
                false_negative=fn,
                detected=tp > 0,
                detection_delay_days=delay,
            ),
            predictions,
        )

    @staticmethod
    def _aggregate(detector_name: str, case_results: list[CaseEvaluation]) -> DetectorEvaluation:
        selected = [result for result in case_results if result.detector == detector_name]
        tp = sum(result.true_positive for result in selected)
        fp = sum(result.false_positive for result in selected)
        tn = sum(result.true_negative for result in selected)
        fn = sum(result.false_negative for result in selected)
        detected_scenarios = sum(result.detected for result in selected)
        delays = [
            result.detection_delay_days
            for result in selected
            if result.detection_delay_days is not None
        ]
        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        return DetectorEvaluation(
            detector=detector_name,
            eligible_points=sum(result.eligible_points for result in selected),
            positive_points=tp + fn,
            predicted_points=tp + fp,
            true_positive=tp,
            false_positive=fp,
            true_negative=tn,
            false_negative=fn,
            precision=round(precision, 6),
            recall=round(recall, 6),
            f1=round(_safe_divide(2 * tp, 2 * tp + fp + fn), 6),
            false_positive_rate=round(_safe_divide(fp, fp + tn), 6),
            detected_scenarios=detected_scenarios,
            scenario_count=len(selected),
            scenario_recall=round(_safe_divide(detected_scenarios, len(selected)), 6),
            mean_detection_delay_days=round(fmean(delays), 6) if delays else None,
        )
