from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from ecom_insight.api import ApiSettings, create_app


def _create_api_database(path: Path) -> str:
    attribution_id = "a" * 24
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE mart_shop_performance_daily (
                date DATE, platform_type VARCHAR, shop_id VARCHAR,
                paid_amount DOUBLE, paid_orders BIGINT,
                refund_amount_by_pay_time DOUBLE, ad_spend DOUBLE,
                settlement_amount_by_pay_time DOUBLE
            )
            """
        )
        connection.execute(
            "INSERT INTO mart_shop_performance_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (date(2025, 1, 20), "douyin", "Shop_A", 100, 2, 3, 10, 85),
        )
        connection.execute(
            """
            CREATE TABLE fact_attribution (
                attribution_id VARCHAR, entity_id VARCHAR, date DATE,
                target_metric VARCHAR, anomaly_score DOUBLE, severity VARCHAR,
                rule_id VARCHAR, cause_code VARCHAR, cause VARCHAR,
                evidence_status VARCHAR, confidence DOUBLE,
                detector_names_json JSON
            )
            """
        )
        connection.execute(
            "INSERT INTO fact_attribution VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attribution_id,
                "Shop_A",
                date(2025, 1, 20),
                "paid_amount",
                3,
                "high",
                "R001",
                "traffic_decline",
                "流量下降",
                "supported_inference",
                0.9,
                '["fixed_threshold"]',
            ),
        )
    return attribution_id


def test_health_overview_and_feedback(tmp_path: Path) -> None:
    database = tmp_path / "warehouse.duckdb"
    attribution_id = _create_api_database(database)
    app = create_app(
        ApiSettings(
            database_path=database,
            feedback_database_path=tmp_path / "feedback.sqlite",
        )
    )
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    overview = client.get("/api/overview")
    assert overview.status_code == 200
    assert overview.json()["kpis"][0]["value"] == 100

    feedback = client.post(
        f"/api/anomalies/{attribution_id}/feedback",
        json={
            "decision": "corrected",
            "corrected_cause_code": "campaign_calendar",
            "notes": "活动日待复核",
            "reviewer_alias": "Reviewer_A",
        },
    )
    assert feedback.status_code == 201
    assert feedback.json()["decision"] == "corrected"
    listed = client.get(f"/api/anomalies/{attribution_id}/feedback")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_feedback_rejects_sensitive_patterns(tmp_path: Path) -> None:
    database = tmp_path / "warehouse.duckdb"
    attribution_id = _create_api_database(database)
    client = TestClient(
        create_app(
            ApiSettings(
                database_path=database,
                feedback_database_path=tmp_path / "feedback.sqlite",
            )
        )
    )

    response = client.post(
        f"/api/anomalies/{attribution_id}/feedback",
        json={"decision": "accepted", "notes": "联系 13800138000"},
    )

    assert response.status_code == 422

