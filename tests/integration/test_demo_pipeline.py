"""Demo pipeline smoke test.

Verifies that `ecom-demo` produces a valid DuckDB with synthetic data,
anomalies, attribution and reports. Does not require real business data.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

DEMO_DB = Path("data/demo/processed/ecom_insight_demo.duckdb")
DEMO_SUMMARY = Path("data/demo/processed/demo_build_summary.json")
DEMO_DATA_ROOT = Path("data/demo/generated")

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def demo_db() -> Path:
    if not DEMO_DB.is_file():
        pytest.skip("Run `uv run ecom-demo` before this test")
    return DEMO_DB


def _connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def test_demo_database_exists(demo_db: Path) -> None:
    assert demo_db.is_file()
    assert demo_db.stat().st_size > 0


def test_core_fact_tables_exist(demo_db: Path) -> None:
    with _connect(demo_db) as con:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
    for expected in (
        "fact_shop_daily",
        "fact_product_daily",
        "fact_channel_daily",
        "fact_search_term_daily",
        "fact_inventory_snapshot",
        "fact_settlement",
        "fact_anomaly",
        "fact_attribution",
        "fact_attribution_evidence",
        "mart_shop_performance_daily",
    ):
        assert expected in tables, f"Missing table: {expected}"


def test_all_fact_tables_marked_synthetic(demo_db: Path) -> None:
    with _connect(demo_db) as con:
        for table in (
            "fact_shop_daily",
            "fact_product_daily",
            "fact_channel_daily",
            "fact_settlement",
            "fact_inventory_snapshot",
            "fact_search_term_daily",
        ):
            row = con.execute(
                f"SELECT count(*) FILTER (WHERE synthetic=true), count(*) FROM {table}"
            ).fetchone()
            assert row is not None
            synthetic_count, total = row
            assert total > 0, f"{table} is empty"
            assert synthetic_count == total, (
                f"{table}: {synthetic_count}/{total} rows marked synthetic"
            )


def test_at_least_ten_scenarios(demo_db: Path) -> None:
    with _connect(demo_db) as con:
        row = con.execute(
            "SELECT count(DISTINCT scenario_id) FROM fact_shop_daily WHERE scenario_id IS NOT NULL"
        ).fetchone()
        assert row is not None
        assert row[0] >= 10, f"Expected >=10 scenarios, got {row[0]}"


def test_at_least_one_anomaly(demo_db: Path) -> None:
    with _connect(demo_db) as con:
        row = con.execute("SELECT count(*) FROM fact_anomaly").fetchone()
        assert row is not None
        assert row[0] > 0, "No anomalies detected"


def test_at_least_one_attribution(demo_db: Path) -> None:
    with _connect(demo_db) as con:
        row = con.execute("SELECT count(*) FROM fact_attribution").fetchone()
        assert row is not None
        assert row[0] > 0, "No attribution candidates"


def test_at_least_one_report(demo_db: Path) -> None:
    with _connect(demo_db) as con:
        row = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name='fact_attribution_report'"
        ).fetchone()
        assert row is not None and row[0] == 1
        row = con.execute("SELECT count(*) FROM fact_attribution_report").fetchone()
        assert row is not None
        assert row[0] > 0, "No reports generated"


def test_no_pii_in_demo_data(demo_db: Path) -> None:
    with _connect(demo_db) as con:
        cols = [
            row[1]
            for row in con.execute(
                "SELECT * FROM information_schema.columns WHERE table_name='fact_shop_daily'"
            ).fetchall()
        ]
    for forbidden in ("receiver_name", "receiver_phone", "receiver_address", "order_no"):
        assert forbidden not in cols, f"Forbidden PII column {forbidden} in fact_shop_daily"


def test_demo_summary_is_synthetic() -> None:
    if not DEMO_SUMMARY.is_file():
        pytest.skip("Run `uv run ecom-demo` before this test")
    summary = json.loads(DEMO_SUMMARY.read_text(encoding="utf-8"))
    assert summary["synthetic"] is True
    assert summary["scenario_count"] >= 10
    assert summary["report_count"] > 0
    assert summary["unsupported_claim_count"] == 0


def test_api_health_reads_demo_db(demo_db: Path) -> None:
    from fastapi.testclient import TestClient

    from ecom_insight.api.app import create_app
    from ecom_insight.api.settings import ApiSettings

    settings = ApiSettings(
        database_path=demo_db,
        feedback_database_path=Path("data/demo/processed/feedback_demo.sqlite"),
        data_mode="demo",
    )
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database_exists"] is True
    assert body["data_mode"] == "demo"


def test_api_overview_returns_demo_data(demo_db: Path) -> None:
    from fastapi.testclient import TestClient

    from ecom_insight.api.app import create_app
    from ecom_insight.api.settings import ApiSettings

    settings = ApiSettings(
        database_path=demo_db,
        feedback_database_path=Path("data/demo/processed/feedback_demo.sqlite"),
        data_mode="demo",
    )
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/api/overview")
    assert response.status_code == 200
    body = response.json()
    assert len(body["kpis"]) > 0
    assert len(body["trend"]) > 0


def test_api_anomaly_detail_returns_data(demo_db: Path) -> None:
    from fastapi.testclient import TestClient

    from ecom_insight.api.app import create_app
    from ecom_insight.api.settings import ApiSettings

    settings = ApiSettings(
        database_path=demo_db,
        feedback_database_path=Path("data/demo/processed/feedback_demo.sqlite"),
        data_mode="demo",
    )
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/api/anomalies?page=1&page_size=1")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    if body["items"]:
        attribution_id = body["items"][0]["attribution_id"]
        detail = client.get(f"/api/anomalies/{attribution_id}")
        assert detail.status_code == 200
