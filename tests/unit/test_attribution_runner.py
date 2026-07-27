from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb

from ecom_insight.attribution import AttributionRunner
from ecom_insight.attribution.runner import SHOP_EVIDENCE_METRICS


def test_attribution_runner_deduplicates_detectors_and_publishes_evidence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "warehouse.duckdb"
    metric_columns = ",\n".join(f"{metric} DOUBLE" for metric in SHOP_EVIDENCE_METRICS)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            f"""
            CREATE TABLE mart_shop_performance_daily (
                date DATE,
                shop_id VARCHAR,
                {metric_columns}
            )
            """
        )
        start = date(2025, 1, 1)
        rows = []
        for index in range(30):
            traffic_factor = 0.60 if index == 29 else 1.0
            values = {
                "paid_amount": 1000.0 * traffic_factor,
                "exposure_users": 1000.0 * traffic_factor,
                "exposure_click_rate": 0.10,
                "click_conversion_rate": 0.05,
                "avg_order_value": 200.0,
                "refund_amount_by_pay_time": 20.0,
                "refund_rate_by_pay_time": 0.02,
                "ad_spend": 100.0,
                "roas": 10.0 * traffic_factor,
                "gpm": 1000.0,
                "settlement_amount_by_pay_time": 850.0 * traffic_factor,
                "platform_commission": 50.0,
                "creator_commission": 20.0,
            }
            rows.append(
                (
                    start + timedelta(days=index),
                    "Shop_A",
                    *(values[metric] for metric in SHOP_EVIDENCE_METRICS),
                )
            )
        placeholders = ", ".join("?" for _ in range(2 + len(SHOP_EVIDENCE_METRICS)))
        connection.executemany(
            f"INSERT INTO mart_shop_performance_daily VALUES ({placeholders})",
            rows,
        )
        connection.execute(
            """
            CREATE TABLE fact_anomaly (
                entity_type VARCHAR,
                entity_id VARCHAR,
                date DATE,
                metric VARCHAR,
                current_value DOUBLE,
                baseline_value DOUBLE,
                change_rate DOUBLE,
                anomaly_score DOUBLE,
                severity VARCHAR,
                detector VARCHAR,
                evidence_json JSON,
                data_origin VARCHAR
            )
            """
        )
        anomaly_date = start + timedelta(days=29)
        for detector in ("fixed_threshold", "rolling_mad"):
            connection.execute(
                "INSERT INTO fact_anomaly VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "shop",
                    "Shop_A",
                    anomaly_date,
                    "paid_amount",
                    600.0,
                    1000.0,
                    -0.40,
                    4.0,
                    "medium",
                    detector,
                    "[]",
                    "real",
                ),
            )

    result = AttributionRunner(
        database_path=database,
        artifact_root=tmp_path / "artifacts",
    ).run()

    assert result.event_count == 1
    assert result.rule_counts["R001"] == 1
    with duckdb.connect(str(database), read_only=True) as connection:
        detectors, method = connection.execute(
            """
            SELECT detector_names_json, json_extract_string(decomposition_json, '$.method')
            FROM fact_attribution
            WHERE rule_id = 'R001'
            """
        ).fetchone()
        evidence_count = connection.execute(
            "SELECT count(*) FROM fact_attribution_evidence"
        ).fetchone()[0]
    assert "fixed_threshold" in detectors
    assert "rolling_mad" in detectors
    assert method == "log_change"
    assert evidence_count >= 3

