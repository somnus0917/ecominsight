from __future__ import annotations

import os
from pathlib import Path

import pytest

from ecom_insight.config import AppSettings
from ecom_insight.metrics import AnalysisRunner
from ecom_insight.warehouse import WarehouseBuilder


@pytest.mark.integration
def test_audited_snapshot_reconciles_phase0(tmp_path: Path) -> None:
    source_root = os.environ.get("ECOM_SOURCE_ROOT")
    if not source_root:
        pytest.skip("ECOM_SOURCE_ROOT is not configured")

    settings = AppSettings(
        source_root=Path(source_root),
        output_root=tmp_path / "processed",
        salt_file=tmp_path / "secrets" / "hmac_salt",
    )
    result = WarehouseBuilder(settings).build()

    assert result.quality_status == "warn"
    assert result.table_counts["stg_shop_daily"] == 165
    assert result.table_counts["stg_product_daily"] == 186
    assert result.table_counts["stg_order_sanitized"] == 612
    assert result.table_counts["stg_settlement"] == 6198

    analysis = AnalysisRunner(
        database_path=result.database_path,
        metric_config_path=Path("configs/metrics.yaml"),
        artifact_root=tmp_path / "processed" / "artifacts",
        curated_parquet_root=tmp_path / "processed" / "parquet" / "curated",
    ).run()

    assert analysis.metric_count >= 30
    assert analysis.mart_counts["mart_shop_performance_daily"] == 165
    assert analysis.mart_counts["mart_shop_summary"] == 8
    assert analysis.mart_counts["mart_product_summary"] == 60
    assert analysis.mart_counts["mart_inventory_health_latest"] == 1200
    assert analysis.mart_counts["mart_financial_daily"] == 32
