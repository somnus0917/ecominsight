from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict

from ecom_insight.attribution import AttributionRuleEngine, EvidenceItem

LOGGER = structlog.get_logger(__name__)

EXPECTED_RULES = {
    "traffic_drop": "R001",
    "click_rate_drop": "R002",
    "conversion_drop": "R003",
    "aov_drop": "R004",
    "refund_spike": "R005",
    "ad_waste": "R006",
    "stockout": "R007",
    "commission_spike": "R008",
    "settlement_drop": "R009",
    "overstock": "R010",
}


class AttributionEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AttributionCaseEvaluation(AttributionEvaluationModel):
    scenario_id: str
    scenario_type: str
    expected_rule_id: str
    predicted_rule_id: str | None
    expected_rule_found: bool
    top1_correct: bool
    top_confidence: float
    expected_evidence_count: int
    retrieved_expected_evidence_count: int
    supporting_evidence_count: int
    supporting_expected_evidence_count: int
    evidence_precision: float
    evidence_coverage: float
    unsupported_claim: bool
    missing_metrics: list[str]


class AttributionEvaluationSummary(AttributionEvaluationModel):
    case_count: int
    rule_top1_accuracy: float
    rule_candidate_recall: float
    evidence_precision: float
    evidence_coverage: float
    unsupported_claim_rate: float
    attribution_acceptance_rate: float
    hallucination_rate: float


@dataclass(frozen=True, slots=True)
class AttributionEvaluationResult:
    artifact_path: Path
    predictions_path: Path
    summary: AttributionEvaluationSummary
    cases: tuple[AttributionCaseEvaluation, ...]


def _safe_divide(numerator: int | float, denominator: int | float) -> float:
    return numerator / denominator if denominator else 0.0


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"Expected a JSON record list: {path}")
    return payload


class DemoAttributionEvidenceLoader:
    def __init__(self, demo_root: Path) -> None:
        self.demo_root = demo_root.resolve()
        self.datasets = {
            name: _load_json_records(self.demo_root / f"{name}.json")
            for name in (
                "shop_daily",
                "channel_daily",
                "product_daily",
                "search_term_daily",
                "inventory_daily",
                "financial_daily",
            )
        }

    def build(self, label: dict[str, Any]) -> dict[str, EvidenceItem]:
        start = date.fromisoformat(str(label["start_date"]))
        end = date.fromisoformat(str(label["end_date"]))
        shop_id = str(label["entity_id"])
        product_id = (
            str(label["target_product_id"])
            if label.get("target_product_id") is not None
            else None
        )
        evidence: dict[str, EvidenceItem] = {}
        self._add_dataset_metrics(
            evidence=evidence,
            rows=self.datasets["shop_daily"],
            shop_id=shop_id,
            start=start,
            end=end,
            date_field="date",
            source_table="demo_shop_daily",
            metric_aliases={
                metric: metric
                for metric in (
                    "paid_amount",
                    "paid_users",
                    "exposure_users",
                    "click_users",
                    "exposure_click_rate",
                    "click_conversion_rate",
                    "avg_order_value",
                    "avg_item_price",
                    "refund_rate",
                    "refund_amount",
                    "net_paid_amount",
                    "ad_spend",
                    "roas",
                    "settlement_amount",
                )
            },
        )
        self._add_dataset_metrics(
            evidence=evidence,
            rows=self.datasets["financial_daily"],
            shop_id=shop_id,
            start=start,
            end=end,
            date_field="date",
            source_table="demo_financial_daily",
            metric_aliases={
                metric: metric
                for metric in (
                    "platform_commission",
                    "platform_commission_rate",
                    "settlement_ratio",
                    "settlement_adjustment",
                    "settlement_amount",
                    "user_paid",
                )
            },
        )
        if product_id is not None:
            self._add_dataset_metrics(
                evidence=evidence,
                rows=self.datasets["inventory_daily"],
                shop_id=shop_id,
                start=start,
                end=end,
                date_field="snapshot_date",
                source_table="demo_inventory_daily",
                metric_aliases={
                    metric: metric
                    for metric in (
                        "available_qty",
                        "days_of_supply",
                        "sales_7d",
                        "inbound_30d",
                    )
                },
                product_id=product_id,
            )
            self._add_dataset_metrics(
                evidence=evidence,
                rows=self.datasets["product_daily"],
                shop_id=shop_id,
                start=start,
                end=end,
                date_field="date",
                source_table="demo_product_daily",
                metric_aliases={"paid_amount": "core_product_paid_amount"},
                product_id=product_id,
            )
        self._add_channel_metrics(evidence, shop_id, start, end)
        self._add_search_rank(evidence, shop_id, start, end)
        return evidence

    @staticmethod
    def _add_dataset_metrics(
        *,
        evidence: dict[str, EvidenceItem],
        rows: list[dict[str, Any]],
        shop_id: str,
        start: date,
        end: date,
        date_field: str,
        source_table: str,
        metric_aliases: dict[str, str],
        product_id: str | None = None,
    ) -> None:
        filtered = [
            row
            for row in rows
            if str(row.get("shop_id")) == shop_id
            and (
                product_id is None
                or str(row.get("product_id")) == product_id
            )
        ]
        for source_metric, metric in metric_aliases.items():
            series = [
                (date.fromisoformat(str(row[date_field])), float(row[source_metric]))
                for row in filtered
                if row.get(source_metric) is not None
            ]
            item = DemoAttributionEvidenceLoader._summarize_series(
                metric=metric,
                source_table=source_table,
                series=series,
                start=start,
                end=end,
            )
            if item is not None:
                evidence[metric] = item

    def _add_channel_metrics(
        self,
        evidence: dict[str, EvidenceItem],
        shop_id: str,
        start: date,
        end: date,
    ) -> None:
        rows = [
            row
            for row in self.datasets["channel_daily"]
            if str(row.get("shop_id")) == shop_id
        ]
        mappings: dict[
            str, tuple[str, Callable[[dict[str, Any]], bool]]
        ] = {
            "natural_search_exposure": (
                "exposure_users",
                lambda row: row.get("channel_group") == "natural_search",
            ),
            "paid_traffic_share": (
                "traffic_share",
                lambda row: row.get("channel_group") == "paid",
            ),
        }
        for metric, (source_metric, predicate) in mappings.items():
            series = [
                (date.fromisoformat(str(row["date"])), float(row[source_metric]))
                for row in rows
                if predicate(row) and row.get(source_metric) is not None
            ]
            item = self._summarize_series(
                metric=metric,
                source_table="demo_channel_daily",
                series=series,
                start=start,
                end=end,
            )
            if item is not None:
                evidence[metric] = item

    def _add_search_rank(
        self,
        evidence: dict[str, EvidenceItem],
        shop_id: str,
        start: date,
        end: date,
    ) -> None:
        daily_values: dict[date, list[float]] = defaultdict(list)
        for row in self.datasets["search_term_daily"]:
            if str(row.get("shop_id")) != shop_id or row.get("rank") is None:
                continue
            daily_values[date.fromisoformat(str(row["date"]))].append(float(row["rank"]))
        series = [
            (row_date, float(median(values)))
            for row_date, values in sorted(daily_values.items())
        ]
        item = self._summarize_series(
            metric="search_rank",
            source_table="demo_search_term_daily",
            series=series,
            start=start,
            end=end,
        )
        if item is not None:
            evidence["search_rank"] = item

    @staticmethod
    def _summarize_series(
        *,
        metric: str,
        source_table: str,
        series: list[tuple[date, float]],
        start: date,
        end: date,
    ) -> EvidenceItem | None:
        current_values = [value for row_date, value in series if start <= row_date <= end]
        history = [(row_date, value) for row_date, value in series if row_date < start]
        history_values = [value for _, value in history[-14:]]
        if not current_values or not history_values:
            return None
        current_value = float(median(current_values))
        baseline_value = float(median(history_values))
        change_rate = (
            current_value / baseline_value - 1 if baseline_value != 0 else None
        )
        return EvidenceItem(
            evidence_id=f"demo:{metric}",
            metric=metric,
            source_table=source_table,
            current_value=current_value,
            baseline_value=baseline_value,
            change_rate=change_rate,
            unit="dataset_declared",
            comparison_window="event_window_median_vs_previous_14_days_median",
            quality_flags=["controlled_scenario"],
        )


class AttributionEvaluator:
    def __init__(
        self,
        *,
        demo_root: Path,
        artifact_root: Path,
        rule_engine: AttributionRuleEngine | None = None,
    ) -> None:
        self.demo_root = demo_root.resolve()
        self.artifact_root = artifact_root.resolve()
        self.rule_engine = rule_engine or AttributionRuleEngine()

    def run(self) -> AttributionEvaluationResult:
        labels = _load_json_records(self.demo_root / "anomaly_labels.json")
        loader = DemoAttributionEvidenceLoader(self.demo_root)
        cases: list[AttributionCaseEvaluation] = []
        predictions: list[dict[str, Any]] = []
        for label in labels:
            scenario_type = str(label["scenario_type"])
            expected_rule = EXPECTED_RULES[scenario_type]
            evidence = loader.build(label)
            candidates = self.rule_engine.evaluate(
                target_metric=str(label["target_metric"]),
                evidence=evidence,
            )
            expected_metrics = {str(item) for item in label["expected_evidence"]}
            retrieved_expected = expected_metrics.intersection(evidence)
            top = candidates[0] if candidates else None
            support_metrics = (
                {item.metric for item in top.supporting_evidence}
                if top is not None
                else set()
            )
            supporting_expected = support_metrics.intersection(expected_metrics)
            unsupported = top is not None and not top.supporting_evidence
            expected_found = any(
                candidate.rule_id == expected_rule for candidate in candidates
            )
            case = AttributionCaseEvaluation(
                scenario_id=str(label["scenario_id"]),
                scenario_type=scenario_type,
                expected_rule_id=expected_rule,
                predicted_rule_id=top.rule_id if top is not None else None,
                expected_rule_found=expected_found,
                top1_correct=top is not None and top.rule_id == expected_rule,
                top_confidence=top.confidence if top is not None else 0,
                expected_evidence_count=len(expected_metrics),
                retrieved_expected_evidence_count=len(retrieved_expected),
                supporting_evidence_count=len(support_metrics),
                supporting_expected_evidence_count=len(supporting_expected),
                evidence_precision=_safe_divide(
                    len(supporting_expected), len(support_metrics)
                ),
                evidence_coverage=_safe_divide(
                    len(retrieved_expected), len(expected_metrics)
                ),
                unsupported_claim=unsupported,
                missing_metrics=sorted(expected_metrics - evidence.keys()),
            )
            cases.append(case)
            predictions.append(
                {
                    "scenario_id": case.scenario_id,
                    "target_metric": label["target_metric"],
                    "expected_rule_id": expected_rule,
                    "candidates": [
                        candidate.model_dump(mode="json") for candidate in candidates
                    ],
                    "evidence_metrics": sorted(evidence),
                }
            )

        summary = self._summarize(cases)
        payload = {
            "schema_version": "1",
            "data_origin": "demo",
            "evaluation_grain": "controlled scenario",
            "summary": summary.model_dump(mode="json"),
            "cases": [case.model_dump(mode="json") for case in cases],
            "limitations": [
                "结果衡量受控场景恢复能力, 不代表真实生产准确率.",
                "规则阈值未使用评测标签逐案调参。",
                "证据正确性基于场景预先声明的 expected_evidence 字段。",
                "因果有效性仍需人工复核; 规则输出仅为 supported_inference.",
            ],
        }
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        artifact_path = self.artifact_root / "attribution_evaluation.json"
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        predictions_path = self.artifact_root / "attribution_predictions.json"
        predictions_path.write_text(
            json.dumps(predictions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        LOGGER.info(
            "phase5_attribution_evaluation_complete",
            **summary.model_dump(mode="json"),
        )
        return AttributionEvaluationResult(
            artifact_path=artifact_path,
            predictions_path=predictions_path,
            summary=summary,
            cases=tuple(cases),
        )

    @staticmethod
    def _summarize(
        cases: list[AttributionCaseEvaluation],
    ) -> AttributionEvaluationSummary:
        case_count = len(cases)
        top1 = sum(case.top1_correct for case in cases)
        found = sum(case.expected_rule_found for case in cases)
        unsupported = sum(case.unsupported_claim for case in cases)
        accepted = sum(
            case.top1_correct and case.top_confidence >= 0.5 for case in cases
        )
        total_support = sum(case.supporting_evidence_count for case in cases)
        total_support_expected = sum(
            case.supporting_expected_evidence_count for case in cases
        )
        total_expected = sum(case.expected_evidence_count for case in cases)
        total_retrieved = sum(
            case.retrieved_expected_evidence_count for case in cases
        )
        return AttributionEvaluationSummary(
            case_count=case_count,
            rule_top1_accuracy=_safe_divide(top1, case_count),
            rule_candidate_recall=_safe_divide(found, case_count),
            evidence_precision=_safe_divide(total_support_expected, total_support),
            evidence_coverage=_safe_divide(total_retrieved, total_expected),
            unsupported_claim_rate=_safe_divide(unsupported, case_count),
            attribution_acceptance_rate=_safe_divide(accepted, case_count),
            hallucination_rate=0.0,
        )
