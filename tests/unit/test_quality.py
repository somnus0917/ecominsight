from __future__ import annotations

from ecom_insight.warehouse.quality import evaluate_quality


def test_quality_fails_duplicate_candidate_key() -> None:
    row = {
        "shop_id": "Shop_synthetic",
        "date": "2026-01-01",
        "exposure_click_rate_users": 0.1,
    }
    report = evaluate_quality({"stg_shop_daily": [row, dict(row)]})

    assert report.failed
    assert any(check.check_id == "unique_key" and check.status == "fail" for check in report.checks)
