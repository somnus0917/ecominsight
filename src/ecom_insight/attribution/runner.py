from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

import duckdb
import structlog

from ecom_insight.attribution.decomposition import decompose_paid_amount
from ecom_insight.attribution.models import (
    AttributionCandidate,
    AttributionResult,
    ConfidenceBreakdown,
    EvidenceItem,
)
from ecom_insight.attribution.rules import AttributionRuleEngine

LOGGER = structlog.get_logger(__name__)

SHOP_EVIDENCE_METRICS = (
    "paid_amount",
    "exposure_users",
    "exposure_click_rate",
    "click_conversion_rate",
    "avg_order_value",
    "refund_amount_by_pay_time",
    "refund_rate_by_pay_time",
    "ad_spend",
    "roas",
    "gpm",
    "settlement_amount_by_pay_time",
    "platform_commission",
    "creator_commission",
)
METRIC_UNITS = {
    "paid_amount": "CNY",
    "exposure_users": "person",
    "exposure_click_rate": "ratio_0_1",
    "click_conversion_rate": "ratio_0_1",
    "avg_order_value": "CNY_per_order",
    "refund_amount_by_pay_time": "CNY",
    "refund_rate_by_pay_time": "ratio_0_1",
    "ad_spend": "CNY",
    "roas": "ratio",
    "gpm": "CNY_per_1000_exposures",
    "settlement_amount_by_pay_time": "CNY",
    "platform_commission": "CNY",
    "creator_commission": "CNY",
    "natural_search_exposure": "person",
    "captured_product_paid_amount": "CNY",
}


@dataclass(frozen=True, slots=True)
class AnomalyEvent:
    entity_type: str
    entity_id: str
    date: date
    metric: str
    detector_names: tuple[str, ...]
    anomaly_score: float
    severity: str


@dataclass(frozen=True, slots=True)
class AttributionRunResult:
    database_path: Path
    artifact_path: Path
    event_count: int
    candidate_count: int
    evidence_count: int
    rule_counts: dict[str, int]


class AttributionRunner:
    def __init__(
        self,
        *,
        database_path: Path,
        artifact_root: Path,
        rule_engine: AttributionRuleEngine | None = None,
    ) -> None:
        self.database_path = database_path.resolve()
        self.artifact_root = artifact_root.resolve()
        self.rule_engine = rule_engine or AttributionRuleEngine()

    def run(self) -> AttributionRunResult:
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.database_path)) as connection:
            self._require_tables(connection)
            events = self._load_events(connection)
            shop_rows = self._load_shop_rows(connection)
            channel_rows = self._load_optional_daily_metric(
                connection,
                table="fact_channel_daily",
                metric="natural_search_exposure",
                value_expression=(
                    "sum(metric_value) FILTER (WHERE channel_group = 'organic_search' "
                    "AND channel_level = 'source')"
                ),
            )
            product_rows = self._load_optional_daily_metric(
                connection,
                table="fact_product_daily",
                metric="captured_product_paid_amount",
                value_expression="sum(paid_amount)",
            )
            results = [
                self._attribute_event(
                    event=event,
                    shop_rows=shop_rows,
                    channel_rows=channel_rows,
                    product_rows=product_rows,
                )
                for event in events
            ]
            evidence_count = self._publish(connection, results)

        candidates = [
            candidate for result in results for candidate in result.candidates
        ]
        rule_counts = dict(Counter(candidate.rule_id for candidate in candidates))
        payload = {
            "schema_version": "1",
            "data_origin": "real",
            "event_grain": "entity x date x metric",
            "event_count": len(results),
            "candidate_count": len(candidates),
            "evidence_count": evidence_count,
            "rule_counts": rule_counts,
            "status_counts": dict(Counter(candidate.status for candidate in candidates)),
            "limitations": [
                "同一异常的多个检测器信号已合并为一个事件。",
                "基线使用同一店铺最近14个有效观察的中位数, 不把缺失日补零.",
                "商品和渠道证据仅在同店同日直接关联, 并保留部分覆盖标记.",
                "平台商品与WMS库存缺少已确认桥接, 真实结果不输出库存因果结论.",
                "结算流水与店铺日报缺少可靠订单桥接, 财务侧候选保持数据不足说明.",
            ],
        }
        artifact_path = self.artifact_root / "phase5_attribution_summary.json"
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        LOGGER.info(
            "phase5_attribution_complete",
            event_count=len(results),
            candidate_count=len(candidates),
            rule_counts=rule_counts,
        )
        return AttributionRunResult(
            database_path=self.database_path,
            artifact_path=artifact_path,
            event_count=len(results),
            candidate_count=len(candidates),
            evidence_count=evidence_count,
            rule_counts=rule_counts,
        )

    @staticmethod
    def _require_tables(connection: duckdb.DuckDBPyConnection) -> None:
        present = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name IN ('fact_anomaly', 'mart_shop_performance_daily')
                """
            ).fetchall()
        }
        missing = {"fact_anomaly", "mart_shop_performance_daily"} - present
        if missing:
            raise ValueError(
                f"Run Phase 3 and Phase 4 before attribution; missing: {sorted(missing)}"
            )

    @staticmethod
    def _load_events(connection: duckdb.DuckDBPyConnection) -> list[AnomalyEvent]:
        rows = connection.execute(
            """
            SELECT
                entity_type,
                entity_id,
                date,
                metric,
                string_agg(DISTINCT detector, ',' ORDER BY detector) AS detectors,
                max(anomaly_score) AS anomaly_score,
                CASE
                    WHEN count(*) FILTER (WHERE severity = 'high') > 0 THEN 'high'
                    WHEN count(*) FILTER (WHERE severity = 'medium') > 0 THEN 'medium'
                    ELSE 'low'
                END AS severity
            FROM fact_anomaly
            WHERE data_origin = 'real'
            GROUP BY entity_type, entity_id, date, metric
            ORDER BY date, entity_id, metric
            """
        ).fetchall()
        events: list[AnomalyEvent] = []
        for row in rows:
            event_date = row[2]
            if not isinstance(event_date, date):
                raise TypeError("Expected DuckDB DATE for attribution event")
            events.append(
                AnomalyEvent(
                    entity_type=str(row[0]),
                    entity_id=str(row[1]),
                    date=event_date,
                    metric=str(row[3]),
                    detector_names=tuple(str(row[4]).split(",")),
                    anomaly_score=float(row[5]),
                    severity=str(row[6]),
                )
            )
        return events

    @staticmethod
    def _load_shop_rows(
        connection: duckdb.DuckDBPyConnection,
    ) -> dict[str, list[dict[str, Any]]]:
        columns = ", ".join(SHOP_EVIDENCE_METRICS)
        rows = connection.execute(
            f"""
            SELECT date, shop_id, {columns}
            FROM mart_shop_performance_daily
            ORDER BY shop_id, date
            """
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            row_date = row[0]
            if not isinstance(row_date, date):
                raise TypeError("Expected DuckDB DATE for shop evidence")
            grouped[str(row[1])].append(
                {
                    "date": row_date,
                    **{
                        metric: float(value) if value is not None else None
                        for metric, value in zip(
                            SHOP_EVIDENCE_METRICS, row[2:], strict=True
                        )
                    },
                }
            )
        return dict(grouped)

    @staticmethod
    def _load_optional_daily_metric(
        connection: duckdb.DuckDBPyConnection,
        *,
        table: str,
        metric: str,
        value_expression: str,
    ) -> dict[str, list[dict[str, Any]]]:
        exists = connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [table],
        ).fetchone()
        if exists is None or int(exists[0]) == 0:
            return {}
        date_column = "date"
        rows = connection.execute(
            f"""
            SELECT {date_column}, shop_id, {value_expression} AS metric_value
            FROM {table}
            GROUP BY {date_column}, shop_id
            ORDER BY shop_id, {date_column}
            """
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row_date, shop_id, value in rows:
            if isinstance(row_date, date) and value is not None:
                grouped[str(shop_id)].append(
                    {"date": row_date, metric: float(value)}
                )
        return dict(grouped)

    def _attribute_event(
        self,
        *,
        event: AnomalyEvent,
        shop_rows: dict[str, list[dict[str, Any]]],
        channel_rows: dict[str, list[dict[str, Any]]],
        product_rows: dict[str, list[dict[str, Any]]],
    ) -> AttributionResult:
        attribution_id = hashlib.sha256(
            f"{event.entity_type}|{event.entity_id}|{event.date}|{event.metric}".encode()
        ).hexdigest()[:24]
        evidence: dict[str, EvidenceItem] = {}
        missing: list[str] = []
        self._add_evidence_from_rows(
            evidence=evidence,
            attribution_id=attribution_id,
            event=event,
            rows=shop_rows.get(event.entity_id, []),
            metrics=SHOP_EVIDENCE_METRICS,
            source_table="mart_shop_performance_daily",
        )
        self._add_evidence_from_rows(
            evidence=evidence,
            attribution_id=attribution_id,
            event=event,
            rows=channel_rows.get(event.entity_id, []),
            metrics=("natural_search_exposure",),
            source_table="fact_channel_daily",
            partial_coverage=True,
        )
        self._add_evidence_from_rows(
            evidence=evidence,
            attribution_id=attribution_id,
            event=event,
            rows=product_rows.get(event.entity_id, []),
            metrics=("captured_product_paid_amount",),
            source_table="fact_product_daily",
            partial_coverage=True,
        )
        if event.metric not in evidence:
            missing.append(f"异常指标 {event.metric} 缺少同日店铺事实。")
        if "natural_search_exposure" not in evidence:
            missing.append("同店同日渠道证据不可用。")
        if "captured_product_paid_amount" not in evidence:
            missing.append("同店同日商品贡献证据不可用。")

        current = {
            metric: item.current_value for metric, item in evidence.items()
        }
        baseline = {
            metric: item.baseline_value for metric, item in evidence.items()
        }
        decomposition = (
            decompose_paid_amount(current=current, baseline=baseline)
            if event.metric == "paid_amount"
            else None
        )
        candidates = self.rule_engine.evaluate(
            target_metric=event.metric,
            evidence=evidence,
        )
        if not candidates:
            candidates = [self._insufficient_candidate(event.metric, evidence, missing)]
        missing.extend(
            information
            for candidate in candidates
            for information in candidate.missing_information
            if information not in missing
        )
        return AttributionResult(
            attribution_id=attribution_id,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            date=event.date,
            target_metric=event.metric,
            detector_names=list(event.detector_names),
            anomaly_score=event.anomaly_score,
            severity=event.severity,  # type: ignore[arg-type]
            decomposition=decomposition,
            candidates=candidates,
            context_evidence=list(evidence.values()),
            missing_information=missing,
            data_origin="real",
        )

    @staticmethod
    def _add_evidence_from_rows(
        *,
        evidence: dict[str, EvidenceItem],
        attribution_id: str,
        event: AnomalyEvent,
        rows: list[dict[str, Any]],
        metrics: tuple[str, ...],
        source_table: str,
        partial_coverage: bool = False,
    ) -> None:
        current_row = next((row for row in rows if row["date"] == event.date), None)
        if current_row is None:
            return
        history = [row for row in rows if row["date"] < event.date][-14:]
        for metric in metrics:
            current_value = current_row.get(metric)
            baseline_values = [
                float(row[metric])
                for row in history
                if row.get(metric) is not None
            ]
            if current_value is None or not baseline_values:
                continue
            baseline_value = float(median(baseline_values))
            change_rate = (
                float(current_value) / baseline_value - 1
                if baseline_value != 0
                else None
            )
            quality_flags: list[str] = []
            if len(baseline_values) < 7:
                quality_flags.append("short_baseline")
            if partial_coverage:
                quality_flags.append("partial_coverage")
            evidence[metric] = EvidenceItem(
                evidence_id=f"{attribution_id}:{metric}",
                metric=metric,
                source_table=source_table,
                current_value=float(current_value),
                baseline_value=baseline_value,
                change_rate=change_rate,
                unit=METRIC_UNITS.get(metric, "unknown"),
                comparison_window="previous_14_observations_median",
                quality_flags=quality_flags,
            )

    @staticmethod
    def _insufficient_candidate(
        target_metric: str,
        evidence: dict[str, EvidenceItem],
        missing: list[str],
    ) -> AttributionCandidate:
        breakdown = ConfidenceBreakdown(
            evidence_completeness=0,
            source_reliability=1,
            directional_consistency=0,
            temporal_alignment=1,
            contradiction_penalty=0,
        )
        target = evidence.get(target_metric)
        return AttributionCandidate(
            rule_id="R000",
            cause_code="insufficient_evidence",
            cause="当前证据不足以形成归因候选",
            status="insufficient_data",
            confidence=0,
            confidence_breakdown=breakdown,
            supporting_evidence=[target] if target is not None else [],
            missing_information=missing or ["规则前置条件未满足。"],
            explanation="保留异常事实, 但不推测未被数据支持的业务原因.",
        )

    @staticmethod
    def _publish(
        connection: duckdb.DuckDBPyConnection,
        results: list[AttributionResult],
    ) -> int:
        connection.execute(
            """
            CREATE OR REPLACE TABLE fact_attribution (
                attribution_id VARCHAR NOT NULL,
                entity_type VARCHAR NOT NULL,
                entity_id VARCHAR NOT NULL,
                date DATE NOT NULL,
                target_metric VARCHAR NOT NULL,
                detector_names_json JSON NOT NULL,
                anomaly_score DOUBLE NOT NULL,
                severity VARCHAR NOT NULL,
                rule_id VARCHAR NOT NULL,
                cause_code VARCHAR NOT NULL,
                cause VARCHAR NOT NULL,
                evidence_status VARCHAR NOT NULL,
                confidence DOUBLE NOT NULL,
                confidence_breakdown_json JSON NOT NULL,
                explanation VARCHAR NOT NULL,
                missing_information_json JSON NOT NULL,
                decomposition_json JSON,
                data_origin VARCHAR NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE fact_attribution_evidence (
                attribution_id VARCHAR NOT NULL,
                rule_id VARCHAR NOT NULL,
                evidence_role VARCHAR NOT NULL,
                evidence_id VARCHAR NOT NULL,
                metric VARCHAR NOT NULL,
                source_table VARCHAR NOT NULL,
                current_value DOUBLE,
                baseline_value DOUBLE,
                change_rate DOUBLE,
                unit VARCHAR NOT NULL,
                comparison_window VARCHAR NOT NULL,
                evidence_status VARCHAR NOT NULL,
                quality_flags_json JSON NOT NULL
            )
            """
        )
        attribution_rows: list[tuple[Any, ...]] = []
        evidence_rows: list[tuple[Any, ...]] = []
        for result in results:
            used_evidence_ids: set[str] = set()
            for candidate in result.candidates:
                attribution_rows.append(
                    (
                        result.attribution_id,
                        result.entity_type,
                        result.entity_id,
                        result.date,
                        result.target_metric,
                        json.dumps(result.detector_names, ensure_ascii=False),
                        result.anomaly_score,
                        result.severity,
                        candidate.rule_id,
                        candidate.cause_code,
                        candidate.cause,
                        candidate.status,
                        candidate.confidence,
                        candidate.confidence_breakdown.model_dump_json(),
                        candidate.explanation,
                        json.dumps(
                            [
                                *result.missing_information,
                                *candidate.missing_information,
                            ],
                            ensure_ascii=False,
                        ),
                        (
                            result.decomposition.model_dump_json()
                            if result.decomposition is not None
                            else None
                        ),
                        result.data_origin,
                    )
                )
                for role, items in (
                    ("supporting", candidate.supporting_evidence),
                    ("counter", candidate.counter_evidence),
                ):
                    used_evidence_ids.update(item.evidence_id for item in items)
                    evidence_rows.extend(
                        (
                            result.attribution_id,
                            candidate.rule_id,
                            role,
                            item.evidence_id,
                            item.metric,
                            item.source_table,
                            item.current_value,
                            item.baseline_value,
                            item.change_rate,
                            item.unit,
                            item.comparison_window,
                            item.status,
                            json.dumps(item.quality_flags, ensure_ascii=False),
                        )
                        for item in items
                    )
            evidence_rows.extend(
                (
                    result.attribution_id,
                    "CONTEXT",
                    "context",
                    item.evidence_id,
                    item.metric,
                    item.source_table,
                    item.current_value,
                    item.baseline_value,
                    item.change_rate,
                    item.unit,
                    item.comparison_window,
                    item.status,
                    json.dumps(item.quality_flags, ensure_ascii=False),
                )
                for item in result.context_evidence
                if item.evidence_id not in used_evidence_ids
            )
        if attribution_rows:
            connection.executemany(
                "INSERT INTO fact_attribution VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                attribution_rows,
            )
        if evidence_rows:
            connection.executemany(
                "INSERT INTO fact_attribution_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                evidence_rows,
            )
        return len(evidence_rows)
