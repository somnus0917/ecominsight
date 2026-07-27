from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from ecom_insight.ingestion.base import Record
from ecom_insight.models import QualityCheck, QualityReport
from ecom_insight.privacy import PrivacySanitizer

UNIQUE_KEYS: dict[str, tuple[str, ...]] = {
    "stg_shop_daily": ("shop_id", "date"),
    "stg_product_daily": ("shop_id", "date", "product_id"),
    "stg_inventory_snapshot": ("snapshot_date", "warehouse_id", "sku_id"),
    "stg_inventory_flow_daily": (
        "snapshot_date",
        "flow_date",
        "warehouse_id",
        "sku_id",
        "flow_type",
    ),
    "stg_order_sanitized": ("order_anon_id", "suborder_anon_id"),
    "stg_settlement": ("settlement_line_id",),
    "stg_external_shop_daily": ("shop_id", "date"),
}

RATIO_COLUMNS: dict[str, tuple[str, ...]] = {
    "stg_shop_daily": (
        "exposure_click_rate_users",
        "click_conversion_rate_users",
        "exposure_conversion_rate_users",
        "exposure_click_rate_count",
        "click_conversion_rate_count",
        "exposure_conversion_rate_count",
        "refund_rate_by_pay_time",
    ),
    "stg_product_daily": ("click_rate", "click_conversion_rate"),
    "stg_content_carrier_daily": ("refund_rate", "exposure_conversion_rate"),
    "stg_channel_daily": ("traffic_share",),
}


def evaluate_quality(tables: dict[str, list[Record]]) -> QualityReport:
    checks: list[QualityCheck] = []
    for table_name, rows in tables.items():
        checks.append(
            QualityCheck(
                check_id="row_count_nonzero",
                table=table_name,
                status="pass" if rows else "warn",
                severity="medium",
                message="Adapter produced rows" if rows else "Adapter produced no rows",
                observed=len(rows),
                expected=">0",
            )
        )
        _check_safe_records(table_name, rows, checks)

    for table_name, keys in UNIQUE_KEYS.items():
        rows = tables.get(table_name, [])
        if rows:
            _check_unique(table_name, rows, keys, checks)

    for table_name, columns in RATIO_COLUMNS.items():
        rows = tables.get(table_name, [])
        if rows:
            _check_ratios(table_name, rows, columns, checks)

    _check_parent_coverage(tables, checks)
    _check_inventory_ranges(tables, checks)
    _check_expected_real_counts(tables, checks)

    status: Literal["pass", "warn", "fail"]
    if any(item.status == "fail" for item in checks):
        status = "fail"
    elif any(item.status == "warn" for item in checks):
        status = "warn"
    else:
        status = "pass"
    return QualityReport(generated_at=datetime.now(UTC), status=status, checks=checks)


def _check_safe_records(table_name: str, rows: list[Record], checks: list[QualityCheck]) -> None:
    violations = 0
    for row in rows:
        try:
            PrivacySanitizer.assert_safe_record(row)
        except ValueError:
            violations += 1
    checks.append(
        QualityCheck(
            check_id="privacy_scan",
            table=table_name,
            status="fail" if violations else "pass",
            severity="critical",
            message="Sanitized records contain no blocked PII/credential patterns",
            observed=violations,
            expected=0,
        )
    )


def _check_unique(
    table_name: str,
    rows: list[Record],
    keys: tuple[str, ...],
    checks: list[QualityCheck],
) -> None:
    values = [tuple(row.get(key) for key in keys) for row in rows]
    duplicate_rows = len(values) - len(set(values))
    checks.append(
        QualityCheck(
            check_id="unique_key",
            table=table_name,
            status="fail" if duplicate_rows else "pass",
            severity="high",
            message=f"Candidate key is unique: {keys}",
            observed=duplicate_rows,
            expected=0,
        )
    )


def _check_ratios(
    table_name: str,
    rows: list[Record],
    columns: tuple[str, ...],
    checks: list[QualityCheck],
) -> None:
    invalid = 0
    for row in rows:
        for column in columns:
            value = row.get(column)
            if value is not None and not 0 <= float(value) <= 1:
                invalid += 1
    checks.append(
        QualityCheck(
            check_id="ratio_range",
            table=table_name,
            status="fail" if invalid else "pass",
            severity="high",
            message="True ratio fields are within [0, 1]",
            observed=invalid,
            expected=0,
        )
    )


def _check_parent_coverage(tables: dict[str, list[Record]], checks: list[QualityCheck]) -> None:
    shop_keys = {(row.get("shop_id"), row.get("date")) for row in tables.get("stg_shop_daily", [])}
    for table_name in (
        "stg_channel_daily",
        "stg_content_carrier_daily",
        "stg_product_daily",
        "stg_search_term_daily",
        "stg_traffic_source_daily",
    ):
        child_keys = {(row.get("shop_id"), row.get("date")) for row in tables.get(table_name, [])}
        orphan_keys = child_keys - shop_keys
        checks.append(
            QualityCheck(
                check_id="shop_date_parent",
                table=table_name,
                status="fail" if orphan_keys else "pass",
                severity="high",
                message="All shop-date keys link to shop daily facts",
                observed=len(orphan_keys),
                expected=0,
            )
        )


def _check_inventory_ranges(tables: dict[str, list[Record]], checks: list[QualityCheck]) -> None:
    inventory = tables.get("stg_inventory_snapshot", [])
    if not inventory:
        return
    negative_available = sum(
        1
        for row in inventory
        if row.get("available_qty") is not None and float(row["available_qty"]) < 0
    )
    checks.append(
        QualityCheck(
            check_id="negative_available_inventory",
            table="stg_inventory_snapshot",
            status="warn" if negative_available else "pass",
            severity="medium",
            message="Negative available inventory is retained as an operational state",
            observed=negative_available,
            expected="business_semantics_required",
        )
    )


def _check_expected_real_counts(
    tables: dict[str, list[Record]], checks: list[QualityCheck]
) -> None:
    expected_counts = {
        "stg_shop_daily": 165,
        "stg_product_daily": 186,
        "stg_order_sanitized": 612,
        "stg_settlement": 6198,
        "stg_external_shop_daily": 60,
    }
    for table_name, expected in expected_counts.items():
        if table_name not in tables:
            continue
        observed = len(tables[table_name])
        checks.append(
            QualityCheck(
                check_id="phase0_reconciliation",
                table=table_name,
                status="pass" if observed == expected else "warn",
                severity="medium",
                message=(
                    "Row count reconciles to the Phase 0 audited snapshot; "
                    "different counts are allowed for synthetic or refreshed sources"
                ),
                observed=observed,
                expected=expected,
            )
        )
