from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, cast

import duckdb
import structlog

from ecom_insight.anomaly.config import AnomalyConfig
from ecom_insight.anomaly.detectors import (
    BaseDetector,
    build_detectors_for_metric,
    default_detectors,
)
from ecom_insight.anomaly.models import (
    AnomalyRecord,
    MetricSeries,
    TimeSeriesPoint,
    severity_from_change,
)

LOGGER = structlog.get_logger(__name__)

REAL_SHOP_METRICS = (
    "paid_amount",
    "exposure_users",
    "exposure_click_rate",
    "click_conversion_rate",
    "avg_order_value",
    "refund_rate_by_pay_time",
    "ad_spend",
    "gpm",
    "settlement_amount_by_pay_time",
)


@dataclass(frozen=True, slots=True)
class AnomalyRunResult:
    database_path: Path
    artifact_path: Path
    series_count: int
    scored_point_count: int
    anomaly_count: int
    detector_counts: dict[str, int]


class AnomalyRunner:
    def __init__(
        self,
        database_path: Path,
        artifact_root: Path,
        detectors: tuple[BaseDetector, ...] | None = None,
        config_path: Path | None = Path("configs/anomaly.yaml"),
        data_origin: Literal["real", "demo"] = "real",
    ) -> None:
        self.database_path = database_path.resolve()
        self.artifact_root = artifact_root.resolve()
        self.config_path = config_path.resolve() if config_path is not None else None
        self.data_origin = data_origin
        self.config = AnomalyConfig.load(self.config_path) if self.config_path else AnomalyConfig()
        self.detectors = detectors

    def run(self) -> AnomalyRunResult:
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

        with duckdb.connect(str(self.database_path)) as connection:
            series = self._load_series(connection)
            records, scored_counts = self._detect(series)
            self._publish(connection, records)
            event_count = self._publish_events(connection, records)

        detector_counts: dict[str, int] = defaultdict(int)
        for record in records:
            detector_counts[record.detector] += 1
        summary = {
            "schema_version": "1",
            "data_origin": self.data_origin,
            "series_count": len(series),
            "scored_point_count": sum(scored_counts.values()),
            "anomaly_count": len(records),
            "anomaly_event_count": event_count,
            "detectors": {
                detector.name: {
                    "scored_points": scored_counts.get(detector.name, 0),
                    "anomalies": detector_counts.get(detector.name, 0),
                    "minimum_history": detector.minimum_history,
                }
                for detector in (self.detectors or default_detectors(self.config))
            },
            "metrics": list(REAL_SHOP_METRICS),
            "config_path": str(self.config_path) if self.config_path else None,
            "limitations": [
                "Missing calendar dates are not imputed as zero.",
                "Each metric and shop is scored independently.",
                "Alerts are statistical signals and are not causal conclusions.",
                "Short series are skipped by each detector's minimum-history gate.",
            ],
        }
        artifact_path = self.artifact_root / "phase4_real_anomalies.json"
        artifact_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        LOGGER.info(
            "phase4_real_anomaly_complete",
            series_count=len(series),
            anomaly_count=len(records),
            detector_counts=dict(detector_counts),
        )
        return AnomalyRunResult(
            database_path=self.database_path,
            artifact_path=artifact_path,
            series_count=len(series),
            scored_point_count=sum(scored_counts.values()),
            anomaly_count=len(records),
            detector_counts=dict(detector_counts),
        )

    @staticmethod
    def _load_series(
        connection: duckdb.DuckDBPyConnection,
    ) -> list[MetricSeries]:
        table_exists = connection.execute(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_name = 'mart_shop_performance_daily'
            """
        ).fetchone()
        if table_exists is None or int(table_exists[0]) == 0:
            raise ValueError("Run Phase 3 analysis before anomaly detection")

        select_metrics = ", ".join(f'"{metric}"' for metric in REAL_SHOP_METRICS)
        rows = connection.execute(
            f"""
            SELECT date, shop_id, {select_metrics}
            FROM mart_shop_performance_daily
            ORDER BY shop_id, date
            """
        ).fetchall()
        grouped: dict[tuple[str, str], list[TimeSeriesPoint]] = defaultdict(list)
        for row in rows:
            row_date = row[0]
            if not isinstance(row_date, date):
                raise TypeError("Expected DuckDB DATE for anomaly series")
            shop_id = str(row[1])
            for metric, raw_value in zip(REAL_SHOP_METRICS, row[2:], strict=True):
                if raw_value is None:
                    continue
                grouped[(shop_id, metric)].append(
                    TimeSeriesPoint(date=row_date, value=float(raw_value))
                )
        return [
            MetricSeries(
                entity_type="shop",
                entity_id=entity_id,
                metric=metric,
                points=tuple(points),
            )
            for (entity_id, metric), points in sorted(grouped.items())
        ]

    def _detect(
        self, series_collection: list[MetricSeries]
    ) -> tuple[list[AnomalyRecord], dict[str, int]]:
        records: list[AnomalyRecord] = []
        scored_counts: dict[str, int] = defaultdict(int)
        for series in series_collection:
            detectors = self.detectors or build_detectors_for_metric(series.metric, self.config)
            if not detectors:
                LOGGER.info("metric_not_configured", metric=series.metric)
            for detector in detectors:
                detections = detector.detect(series)
                scored_counts[detector.name] += len(detections)
                for detection in detections:
                    if not detection.is_anomaly:
                        continue
                    records.append(
                        AnomalyRecord(
                            entity_type=series.entity_type,
                            entity_id=series.entity_id,
                            date=detection.date,
                            metric=series.metric,
                            current_value=detection.current_value,
                            baseline_value=detection.baseline_value,
                            change_rate=detection.change_rate,
                            anomaly_score=detection.anomaly_score,
                            severity=severity_from_change(detection.change_rate),
                            detector=detector.name,
                            evidence=[
                                {
                                    "evidence_type": "historical_baseline",
                                    "history_size": detection.history_size,
                                    "source": "mart_shop_performance_daily",
                                    "status": "confirmed_fact",
                                    "trigger_type": detection.trigger_type,
                                    "trigger_threshold": detection.trigger_threshold,
                                }
                            ],
                            data_origin=self.data_origin,
                        )
                    )
        return records, dict(scored_counts)

    @staticmethod
    def _publish(connection: duckdb.DuckDBPyConnection, records: list[AnomalyRecord]) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE fact_anomaly (
                entity_type VARCHAR NOT NULL,
                entity_id VARCHAR NOT NULL,
                date DATE NOT NULL,
                metric VARCHAR NOT NULL,
                current_value DOUBLE NOT NULL,
                baseline_value DOUBLE NOT NULL,
                change_rate DOUBLE,
                anomaly_score DOUBLE NOT NULL,
                severity VARCHAR NOT NULL,
                detector VARCHAR NOT NULL,
                evidence_json JSON NOT NULL,
                data_origin VARCHAR NOT NULL
            )
            """
        )
        if not records:
            return
        connection.executemany(
            """
            INSERT INTO fact_anomaly VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.entity_type,
                    record.entity_id,
                    record.date,
                    record.metric,
                    record.current_value,
                    record.baseline_value,
                    record.change_rate,
                    record.anomaly_score,
                    record.severity,
                    record.detector,
                    json.dumps(record.evidence, ensure_ascii=False),
                    record.data_origin,
                )
                for record in records
            ],
        )

    def _publish_events(
        self, connection: duckdb.DuckDBPyConnection, records: list[AnomalyRecord]
    ) -> int:
        connection.execute(
            """
            CREATE OR REPLACE TABLE fact_anomaly_event (
                anomaly_event_id VARCHAR PRIMARY KEY, entity_type VARCHAR NOT NULL,
                entity_id VARCHAR NOT NULL, date DATE NOT NULL, metric VARCHAR NOT NULL,
                direction VARCHAR NOT NULL, current_value DOUBLE NOT NULL,
                baseline_value DOUBLE NOT NULL, change_rate DOUBLE, severity VARCHAR NOT NULL,
                aggregation_policy VARCHAR NOT NULL, triggered_detectors_json JSON NOT NULL,
                detector_count INTEGER NOT NULL, weighted_score DOUBLE NOT NULL,
                event_status VARCHAR NOT NULL, event_started_at DATE NOT NULL,
                last_abnormal_at DATE NOT NULL, recovery_started_at DATE, resolved_at DATE,
                data_origin VARCHAR NOT NULL
            )
            """
        )
        grouped: dict[tuple[str, str, date, str, str], list[AnomalyRecord]] = defaultdict(list)
        for record in records:
            direction = "increase" if (record.change_rate or 0) >= 0 else "decline"
            grouped[
                (record.entity_type, record.entity_id, record.date, record.metric, direction)
            ].append(record)
        rows: list[tuple[object, ...]] = []
        config = self.config.aggregation
        for (entity_type, entity_id, event_date, metric, direction), members in grouped.items():
            detectors = sorted({member.detector for member in members})
            weight = sum(
                config.detector_weights.get(
                    cast(Literal["fixed_threshold", "rolling_zscore", "rolling_mad", "isolation_forest"], name),
                    1.0,
                )
                for name in detectors
            )
            accepted = (
                config.policy == "any"
                or (
                    config.policy == "consensus"
                    and len(detectors) >= config.consensus_min_detectors
                )
                or (config.policy == "weighted" and weight >= config.weighted_trigger_threshold)
            )
            if not accepted:
                continue
            first = members[0]
            event_id = f"{entity_type}:{entity_id}:{event_date.isoformat()}:{metric}:{direction}"
            rows.append(
                (
                    event_id,
                    entity_type,
                    entity_id,
                    event_date,
                    metric,
                    direction,
                    first.current_value,
                    first.baseline_value,
                    first.change_rate,
                    max(
                        members, key=lambda item: {"low": 0, "medium": 1, "high": 2}[item.severity]
                    ).severity,
                    config.policy,
                    json.dumps(detectors),
                    len(detectors),
                    weight,
                    "active_anomaly",
                    event_date,
                    event_date,
                    None,
                    None,
                    self.data_origin,
                )
            )
        if rows:
            connection.executemany(
                "INSERT INTO fact_anomaly_event VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)
