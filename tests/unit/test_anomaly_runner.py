from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb

from ecom_insight.anomaly import AnomalyRunner, FixedThresholdDetector


def test_anomaly_runner_publishes_real_alerts(tmp_path: Path) -> None:
    database = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            """
            CREATE TABLE mart_shop_performance_daily (
                date DATE,
                shop_id VARCHAR,
                paid_amount DOUBLE,
                exposure_users DOUBLE,
                exposure_click_rate DOUBLE,
                click_conversion_rate DOUBLE,
                avg_order_value DOUBLE,
                refund_rate_by_pay_time DOUBLE,
                ad_spend DOUBLE,
                gpm DOUBLE,
                settlement_amount_by_pay_time DOUBLE
            )
            """
        )
        start = date(2025, 1, 1)
        rows = []
        for index in range(30):
            paid_amount = 40.0 if index == 20 else 100.0
            rows.append(
                (
                    start + timedelta(days=index),
                    "Shop_A",
                    paid_amount,
                    1000.0,
                    0.10,
                    0.05,
                    200.0,
                    0.03,
                    10.0,
                    100.0,
                    85.0,
                )
            )
        connection.executemany(
            "INSERT INTO mart_shop_performance_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    result = AnomalyRunner(
        database_path=database,
        artifact_root=tmp_path / "artifacts",
        detectors=(FixedThresholdDetector(),),
    ).run()

    assert result.series_count == 9
    assert result.anomaly_count >= 1
    with duckdb.connect(str(database), read_only=True) as connection:
        alerts = connection.execute("SELECT metric, data_origin FROM fact_anomaly").fetchall()
    assert ("paid_amount", "real") in alerts
