"""Demo warehouse builder: synthetic JSON -> DuckDB with real-warehouse schema."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import polars as pl


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class DemoWarehouseResult:
    database_path: Path
    table_counts: dict[str, int]


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _sid(ids: Any) -> str | None:
    if not ids:
        return None
    return ",".join(ids) if isinstance(ids, list) else str(ids)


def _df(records: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(records, infer_schema_length=None) if records else pl.DataFrame()


def _shop_df(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return _df([{
        "date": r.get("date"), "platform_id": r.get("shop_id", ""),
        "platform_type": r.get("platform", "douyin"), "shop_id": r.get("shop_id", ""),
        "shop_name_masked": r.get("shop_name_masked", r.get("shop_id", "")),
        "source_system": "demo", "gmv": r.get("gmv"),
        "paid_amount": r.get("paid_amount"), "net_paid_amount": r.get("net_paid_amount"),
        "paid_orders": r.get("paid_orders"), "paid_items": r.get("paid_items"),
        "paid_users": r.get("paid_users"), "exposure_users": r.get("exposure_users"),
        "exposure_count": r.get("exposure_count"), "click_users": r.get("click_users"),
        "click_count": r.get("click_count"),
        "exposure_click_rate_users": r.get("exposure_click_rate"),
        "click_conversion_rate_users": r.get("click_conversion_rate"),
        "exposure_conversion_rate_users": r.get("exposure_conversion_rate"),
        "refund_amount_by_pay_time": r.get("refund_amount"),
        "refund_rate_by_pay_time": r.get("refund_rate"),
        "settlement_amount_by_pay_time": r.get("settlement_amount"),
        "expense_amount": r.get("expense_amount"), "ad_spend": r.get("ad_spend"),
        "roas": r.get("roas"), "platform_subsidy": r.get("platform_subsidy"),
        "creator_subsidy": r.get("creator_subsidy"),
        "platform_commission": r.get("platform_commission"),
        "creator_commission": r.get("creator_commission"),
        "merchant_experience_score": r.get("merchant_experience_score"),
        "synthetic": True, "scenario_id": _sid(r.get("scenario_ids")),
    } for r in rows])


def _product_df(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return _df([{
        "date": r.get("date"), "platform_id": r.get("shop_id", ""),
        "shop_id": r.get("shop_id", ""), "product_id": r.get("product_id", ""),
        "product_name_masked": r.get("product_id", ""),
        "paid_amount": r.get("paid_amount"), "paid_orders": r.get("paid_orders"),
        "paid_users": r.get("paid_users"), "exposure_users": r.get("exposure_users"),
        "click_users": r.get("click_users"),
        "exposure_click_rate_users": r.get("click_rate"),
        "click_conversion_rate_users": r.get("conversion_rate"),
        "synthetic": True, "scenario_id": _sid(r.get("scenario_ids")),
    } for r in rows])


def _channel_df(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return _df([{
        "date": r.get("date"), "platform_id": r.get("shop_id", ""),
        "shop_id": r.get("shop_id", ""), "channel_id": r.get("channel", ""),
        "channel_group": r.get("channel", ""), "channel_level": "group",
        "source_metric": "exposure_users", "metric_value": r.get("exposure_users"),
        "traffic_share": r.get("exposure_share"), "paid_amount": r.get("paid_amount"),
        "synthetic": True, "scenario_id": _sid(r.get("scenario_ids")),
    } for r in rows])


def _search_df(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return _df([{
        "date": r.get("date"), "platform_id": r.get("shop_id", ""),
        "shop_id": r.get("shop_id", ""), "term_kind": r.get("term_kind", "shop_term"),
        "term_id": r.get("term", ""), "rank": r.get("rank"),
        "paid_amount": r.get("paid_amount"), "exposure_users": r.get("exposure_users"),
        "paid_amount_change_rate": r.get("paid_amount_change"),
        "exposure_change_rate": r.get("exposure_change"),
        "paid_amount_lower": r.get("paid_amount_lower"),
        "paid_amount_upper": r.get("paid_amount_upper"),
        "exposure_lower": r.get("exposure_lower"),
        "exposure_upper": r.get("exposure_upper"),
        "paid_amount_benchmark": r.get("paid_amount_benchmark"),
        "exposure_benchmark": r.get("exposure_benchmark"),
        "synthetic": True, "scenario_id": _sid(r.get("scenario_ids")),
    } for r in rows])


def _inventory_df(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return _df([{
        "snapshot_date": r.get("date") or r.get("snapshot_date"),
        "warehouse_id": r.get("warehouse_id", "Warehouse_demo"),
        "sku_id": r.get("sku_id", ""), "product_id": r.get("product_id", ""),
        "available_qty": r.get("available_qty"), "locked_qty": r.get("locked_qty", 0),
        "on_hand_qty": r.get("on_hand_qty"),
        "stock_qty": r.get("stock_qty") or (r.get("on_hand_qty") or r.get("available_qty", 0)),
        "spec_name": r.get("spec_name", ""), "spec_no": r.get("spec_no", ""),
        "goods_no": r.get("goods_no", ""), "brand": r.get("brand", ""),
        "synthetic": True, "scenario_id": _sid(r.get("scenario_ids")),
    } for r in rows])


def _settlement_df(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return _df([{
        "date": r.get("date"), "settled_at": r.get("date"),
        "shop_id": r.get("shop_id", ""),
        "merchant_entity_id": r.get("merchant_entity_id", ""),
        "order_anon_id": f"Order_demo_{i}",
        "settlement_amount": r.get("settlement_amount"),
        "user_paid": r.get("user_paid"), "income_total": r.get("income_total"),
        "platform_subsidy": r.get("platform_subsidy"),
        "other_platform_subsidy": None,
        "creator_subsidy": r.get("creator_subsidy"),
        "platform_payment_subsidy": None,
        "monthly_payment_marketing_subsidy": None,
        "bank_subsidy": None,
        "platform_commission": r.get("platform_commission"),
        "creator_commission": r.get("creator_commission"),
        "platform_service_fee": r.get("platform_service_fee"),
        "service_provider_commission": None,
        "channel_share": None,
        "merchant_acquisition_service_fee": None,
        "offsite_promotion_fee": None,
        "other_share": None,
        "other_expense": r.get("other_expense"),
        "refund": r.get("refund"),
        "settlement_adjustment": r.get("settlement_adjustment"),
        "expense_total": r.get("expense_total"),
        "pre_settlement_refund": None,
        "commission_waived": None,
        "platform_commission_rate": r.get("platform_commission_rate"),
        "settlement_ratio": r.get("settlement_ratio"),
        "synthetic": True, "scenario_id": _sid(r.get("scenario_ids")),
    } for i, r in enumerate(rows)])


def _empty(cols: list[str]) -> pl.DataFrame:
    return pl.DataFrame({c: [] for c in cols}, infer_schema_length=None)


def _write(con: duckdb.DuckDBPyConnection, name: str, df: pl.DataFrame) -> int:
    if df.is_empty():
        con.register("_t", df)
        con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _t')
        con.unregister("_t")
        return 0
    for col in df.columns:
        if col in ("date", "snapshot_date", "settled_at") or col.endswith("_date"):
            df = df.with_columns(pl.col(col).cast(pl.Date, strict=False))
    con.register("_t", df)
    con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _t')
    con.unregister("_t")
    return len(df)


class DemoWarehouseBuilder:
    """Build a DuckDB warehouse from synthetic demo JSON data."""

    def __init__(self, demo_root: Path, database_path: Path) -> None:
        self.demo_root = demo_root.resolve()
        self.database_path = database_path.resolve()

    def build(self) -> DemoWarehouseResult:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        if self.database_path.exists():
            self.database_path.unlink()

        with duckdb.connect(str(self.database_path)) as con:
            con.execute("SET TimeZone='Asia/Shanghai'")
            counts: dict[str, int] = {}

            counts["fact_shop_daily"] = _write(con, "fact_shop_daily",
                _shop_df(_load_json(self.demo_root / "shop_daily.json")))
            counts["fact_product_daily"] = _write(con, "fact_product_daily",
                _product_df(_load_json(self.demo_root / "product_daily.json")))
            counts["fact_channel_daily"] = _write(con, "fact_channel_daily",
                _channel_df(_load_json(self.demo_root / "channel_daily.json")))
            counts["fact_search_term_daily"] = _write(con, "fact_search_term_daily",
                _search_df(_load_json(self.demo_root / "search_term_daily.json")))
            counts["fact_traffic_source_daily"] = _write(con, "fact_traffic_source_daily",
                _empty(["date", "shop_id", "traffic_source_id", "paid_amount",
                    "exposure_users", "paid_amount_change_rate", "exposure_change_rate",
                    "paid_amount_benchmark", "exposure_benchmark", "synthetic", "scenario_id"]))
            counts["fact_inventory_snapshot"] = _write(con, "fact_inventory_snapshot",
                _inventory_df(_load_json(self.demo_root / "inventory_daily.json")))
            counts["fact_inventory_flow_daily"] = _write(con, "fact_inventory_flow_daily",
                _empty(["snapshot_date", "warehouse_id", "sku_id", "flow_type",
                    "quantity", "synthetic", "scenario_id"]))
            counts["fact_settlement"] = _write(con, "fact_settlement",
                _settlement_df(_load_json(self.demo_root / "financial_daily.json")))
            counts["fact_content_daily"] = _write(con, "fact_content_daily",
                _empty(["date", "platform_id", "shop_id", "content_type",
                    "paid_amount", "synthetic", "scenario_id"]))
            counts["fact_content_carrier_daily"] = _write(con, "fact_content_carrier_daily",
                _empty(["date", "shop_id", "content_type", "paid_amount",
                    "exposure_users", "watch_users", "refund_rate",
                    "exposure_conversion_rate", "gpm", "gpm_benchmark",
                    "synthetic", "scenario_id"]))
            counts["fact_external_shop_daily"] = _write(con, "fact_external_shop_daily",
                _empty(["date", "shop_id", "source_system", "paid_amount",
                    "paid_orders", "paid_items", "synthetic", "scenario_id"]))
            counts["fact_order_sanitized"] = _write(con, "fact_order_sanitized",
                _empty(["order_anon_id", "suborder_anon_id", "date", "shop_id",
                    "product_id", "paid_amount", "synthetic", "scenario_id"]))

            self._create_dimensions(con)
            self._create_views(con)

        return DemoWarehouseResult(database_path=self.database_path, table_counts=counts)

    @staticmethod
    def _create_dimensions(con: duckdb.DuckDBPyConnection) -> None:
        con.execute("""
            CREATE OR REPLACE TABLE dim_date AS
            SELECT DISTINCT date FROM (
                SELECT CAST(date AS DATE) AS date FROM fact_shop_daily WHERE date IS NOT NULL
                UNION SELECT CAST(snapshot_date AS DATE) AS date FROM fact_inventory_snapshot WHERE snapshot_date IS NOT NULL
                UNION SELECT CAST(date AS DATE) AS date FROM fact_settlement WHERE date IS NOT NULL
            ) ORDER BY date
        """)
        con.execute("CREATE OR REPLACE TABLE dim_platform AS SELECT platform_id, min(platform_type) AS platform_type FROM fact_shop_daily GROUP BY platform_id")
        con.execute("""CREATE OR REPLACE TABLE dim_shop AS
            SELECT shop_id, min(shop_name_masked) AS shop_name_masked,
                   min(platform_id) AS platform_id,
                   min(CAST(date AS DATE)) AS first_seen_date,
                   max(CAST(date AS DATE)) AS last_seen_date
            FROM fact_shop_daily GROUP BY shop_id""")
        con.execute("CREATE OR REPLACE TABLE dim_product AS SELECT product_id, min(product_name_masked) AS product_name_masked FROM fact_product_daily GROUP BY product_id")
        con.execute("CREATE OR REPLACE TABLE dim_sku AS SELECT 1::VARCHAR AS sku_id WHERE 1=0")
        con.execute("CREATE OR REPLACE TABLE dim_channel AS SELECT 1::VARCHAR AS channel_id WHERE 1=0")
        con.execute("CREATE OR REPLACE TABLE dim_content_type AS SELECT 1::VARCHAR AS content_type WHERE 1=0")
        con.execute("CREATE OR REPLACE TABLE dim_warehouse AS SELECT DISTINCT warehouse_id FROM fact_inventory_snapshot")
        con.execute("CREATE OR REPLACE TABLE bridge_product_sku AS SELECT 1::VARCHAR AS product_id WHERE 1=0")

    @staticmethod
    def _create_views(con: duckdb.DuckDBPyConnection) -> None:
        con.execute("CREATE OR REPLACE VIEW vw_shop_daily_metrics AS SELECT * FROM fact_shop_daily")
        con.execute("CREATE OR REPLACE VIEW vw_latest_inventory AS SELECT * FROM fact_inventory_snapshot WHERE 1=0")
