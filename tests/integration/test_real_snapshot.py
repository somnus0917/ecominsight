from __future__ import annotations

import os
from pathlib import Path

import pytest

from ecom_insight.config import AppSettings
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
