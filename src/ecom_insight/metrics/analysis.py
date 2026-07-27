from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import structlog

from ecom_insight.metrics.registry import MetricRegistry

LOGGER = structlog.get_logger(__name__)

MART_TABLES = (
    "mart_shop_performance_daily",
    "mart_shop_summary",
    "mart_product_summary",
    "mart_product_shop_coverage_daily",
    "mart_channel_composition_daily",
    "mart_content_type_summary",
    "mart_content_carrier_summary",
    "mart_search_term_summary",
    "mart_traffic_source_summary",
    "mart_inventory_health_latest",
    "mart_inventory_summary_latest",
    "mart_financial_daily",
    "mart_financial_merchant_summary",
)


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    database_path: Path
    summary_path: Path
    mart_counts: dict[str, int]
    metric_count: int


class AnalysisRunner:
    def __init__(
        self,
        database_path: Path,
        metric_config_path: Path,
        artifact_root: Path,
        curated_parquet_root: Path | None = None,
    ) -> None:
        self.database_path = database_path.resolve()
        self.metric_config_path = metric_config_path.resolve()
        self.artifact_root = artifact_root.resolve()
        self.curated_parquet_root = (
            curated_parquet_root.resolve() if curated_parquet_root is not None else None
        )

    def run(self) -> AnalysisResult:
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)
        registry = MetricRegistry.load(self.metric_config_path)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        if self.curated_parquet_root is not None:
            self.curated_parquet_root.mkdir(parents=True, exist_ok=True)

        with duckdb.connect(str(self.database_path)) as connection:
            connection.execute("SET TimeZone='Asia/Shanghai'")
            registry.publish_to_duckdb(connection)
            self._create_shop_marts(connection)
            self._create_product_marts(connection)
            self._create_channel_and_content_marts(connection)
            self._create_search_marts(connection)
            self._create_inventory_marts(connection)
            self._create_financial_marts(connection)
            self._create_analysis_quality(connection)
            mart_counts = {
                table: _scalar_int(connection, f'SELECT count(*) FROM "{table}"')
                for table in MART_TABLES
            }
            if self.curated_parquet_root is not None:
                self._export_marts(connection)
            summary = self._build_summary(connection, registry, mart_counts)

        summary_path = self.artifact_root / "phase3_summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        LOGGER.info(
            "phase3_analysis_complete",
            metric_count=len(registry.config.metrics),
            mart_counts=mart_counts,
        )
        return AnalysisResult(
            database_path=self.database_path,
            summary_path=summary_path,
            mart_counts=mart_counts,
            metric_count=len(registry.config.metrics),
        )

    @staticmethod
    def _create_shop_marts(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_shop_performance_daily AS
            SELECT
                date,
                platform_id,
                platform_type,
                shop_id,
                source_system,
                paid_amount,
                gmv,
                paid_orders,
                paid_items,
                paid_users,
                exposure_users,
                click_users,
                CASE WHEN paid_users > 0
                     THEN CAST(paid_amount / paid_users AS DECIMAL(18,2)) END
                    AS avg_order_value,
                CASE WHEN paid_items > 0
                     THEN CAST(paid_amount / paid_items AS DECIMAL(18,2)) END
                    AS avg_item_price,
                CASE WHEN exposure_users > 0
                     THEN CAST(click_users AS DOUBLE) / exposure_users END
                    AS exposure_click_rate,
                CASE WHEN click_users > 0
                     THEN CAST(paid_users AS DOUBLE) / click_users END
                    AS click_conversion_rate,
                CASE WHEN exposure_users > 0
                     THEN CAST(paid_users AS DOUBLE) / exposure_users END
                    AS exposure_conversion_rate,
                CASE WHEN exposure_users > 0
                     THEN CAST(paid_amount * 1000 / exposure_users AS DECIMAL(18,2)) END
                    AS gpm,
                refund_amount_by_pay_time,
                refund_rate_by_pay_time,
                ad_spend,
                CASE WHEN ad_spend > 0
                     THEN CAST(paid_amount / ad_spend AS DECIMAL(18,4)) END AS roas,
                settlement_amount_by_pay_time,
                platform_subsidy,
                creator_subsidy,
                platform_commission,
                creator_commission,
                merchant_experience_score
            FROM fact_shop_daily
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_shop_summary AS
            SELECT
                platform_id,
                platform_type,
                shop_id,
                source_system,
                min(date) AS first_date,
                max(date) AS last_date,
                count(*) AS observation_days,
                sum(paid_amount) AS paid_amount,
                sum(gmv) AS gmv,
                sum(paid_orders) AS paid_orders,
                sum(paid_items) AS paid_items,
                sum(paid_users) AS paid_users_day_sum,
                sum(exposure_users) AS exposure_users_day_sum,
                sum(click_users) AS click_users_day_sum,
                CASE WHEN sum(paid_users) > 0
                     THEN CAST(sum(paid_amount) / sum(paid_users) AS DECIMAL(18,2)) END
                    AS avg_order_value,
                CASE WHEN sum(paid_items) > 0
                     THEN CAST(sum(paid_amount) / sum(paid_items) AS DECIMAL(18,2)) END
                    AS avg_item_price,
                CASE WHEN sum(exposure_users) > 0
                     THEN CAST(sum(click_users) AS DOUBLE) / sum(exposure_users) END
                    AS exposure_click_rate,
                CASE WHEN sum(click_users) > 0
                     THEN CAST(sum(paid_users) AS DOUBLE) / sum(click_users) END
                    AS click_conversion_rate,
                sum(ad_spend) AS ad_spend,
                CASE WHEN sum(ad_spend) > 0
                     THEN CAST(sum(paid_amount) / sum(ad_spend) AS DECIMAL(18,4)) END AS roas,
                count(ad_spend) / count(*)::DOUBLE AS ad_spend_coverage,
                count(refund_rate_by_pay_time) / count(*)::DOUBLE AS refund_rate_coverage,
                avg(refund_rate_by_pay_time) AS refund_rate_daily_mean,
                avg(merchant_experience_score) AS experience_score_mean
            FROM mart_shop_performance_daily
            GROUP BY platform_id, platform_type, shop_id, source_system
            """
        )

    @staticmethod
    def _create_product_marts(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_product_summary AS
            WITH product AS (
                SELECT
                    shop_id,
                    product_id,
                    min(product_name_masked) AS product_name_masked,
                    min(date) AS first_date,
                    max(date) AS last_date,
                    count(*) AS observation_days,
                    sum(paid_amount) AS paid_amount,
                    sum(paid_orders) AS paid_orders,
                    sum(paid_users) AS paid_users_day_sum,
                    sum(exposure_users) AS exposure_users_day_sum,
                    sum(click_users) AS click_users_day_sum,
                    CASE WHEN sum(exposure_users) > 0
                         THEN sum(click_users)::DOUBLE / sum(exposure_users) END AS click_rate,
                    CASE WHEN sum(click_users) > 0
                         THEN sum(paid_users)::DOUBLE / sum(click_users) END
                        AS click_conversion_rate
                FROM fact_product_daily
                GROUP BY shop_id, product_id
            )
            SELECT *,
                   CASE WHEN sum(paid_amount) OVER (PARTITION BY shop_id) <> 0
                        THEN paid_amount / sum(paid_amount) OVER (PARTITION BY shop_id) END
                       AS paid_amount_share_in_captured_products,
                   dense_rank() OVER (PARTITION BY shop_id ORDER BY paid_amount DESC)
                       AS paid_amount_rank
            FROM product
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_product_shop_coverage_daily AS
            WITH product AS (
                SELECT date, shop_id, sum(paid_amount) AS product_paid_amount
                FROM fact_product_daily
                GROUP BY date, shop_id
            )
            SELECT
                p.date,
                p.shop_id,
                p.product_paid_amount,
                s.paid_amount AS shop_paid_amount,
                CASE WHEN s.paid_amount <> 0
                     THEN p.product_paid_amount / s.paid_amount END AS captured_product_coverage
            FROM product p
            LEFT JOIN fact_shop_daily s USING (date, shop_id)
            """
        )

    @staticmethod
    def _create_channel_and_content_marts(
        connection: duckdb.DuckDBPyConnection,
    ) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_channel_composition_daily AS
            SELECT date, shop_id, channel_id, channel_group, source_metric,
                   metric_value, traffic_share
            FROM fact_channel_daily
            WHERE channel_level = 'group'
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_content_type_summary AS
            WITH content AS (
                SELECT shop_id, content_type,
                       min(date) AS first_date,
                       max(date) AS last_date,
                       count(*) AS observation_days,
                       sum(paid_amount) AS paid_amount
                FROM fact_content_daily
                GROUP BY shop_id, content_type
            )
            SELECT *,
                   CASE WHEN sum(paid_amount) OVER (PARTITION BY shop_id) <> 0
                        THEN paid_amount / sum(paid_amount) OVER (PARTITION BY shop_id) END
                       AS paid_amount_share
            FROM content
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_content_carrier_summary AS
            SELECT
                shop_id,
                content_type,
                min(date) AS first_date,
                max(date) AS last_date,
                count(*) AS observation_days,
                sum(paid_amount) AS paid_amount,
                sum(exposure_users) AS exposure_users_day_sum,
                sum(watch_users) AS watch_users_day_sum,
                avg(refund_rate) AS refund_rate_daily_mean,
                avg(exposure_conversion_rate) AS exposure_conversion_rate_daily_mean,
                avg(gpm) AS gpm_daily_mean,
                avg(gpm_benchmark) AS gpm_benchmark_daily_mean
            FROM fact_content_carrier_daily
            GROUP BY shop_id, content_type
            """
        )

    @staticmethod
    def _create_search_marts(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_search_term_summary AS
            SELECT
                shop_id,
                term_kind,
                term_id,
                min(date) AS first_date,
                max(date) AS last_date,
                count(*) AS observation_days,
                min(rank) AS best_rank,
                max(rank) AS worst_rank,
                arg_max(rank, date) AS latest_rank,
                sum(paid_amount) AS paid_amount,
                sum(exposure_users) AS exposure_users_day_sum,
                avg(paid_amount_change_rate) AS paid_amount_change_rate_mean,
                avg(exposure_change_rate) AS exposure_change_rate_mean,
                avg(paid_amount_lower) AS paid_amount_lower_mean,
                avg(paid_amount_upper) AS paid_amount_upper_mean,
                avg(exposure_lower) AS exposure_lower_mean,
                avg(exposure_upper) AS exposure_upper_mean
            FROM fact_search_term_daily
            GROUP BY shop_id, term_kind, term_id
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_traffic_source_summary AS
            SELECT
                shop_id,
                traffic_source_id,
                min(date) AS first_date,
                max(date) AS last_date,
                count(*) AS observation_days,
                sum(paid_amount) AS paid_amount,
                sum(exposure_users) AS exposure_users_day_sum,
                avg(paid_amount_change_rate) AS paid_amount_change_rate_mean,
                avg(exposure_change_rate) AS exposure_change_rate_mean,
                avg(paid_amount_benchmark) AS paid_amount_benchmark_mean,
                avg(exposure_benchmark) AS exposure_benchmark_mean
            FROM fact_traffic_source_daily
            GROUP BY shop_id, traffic_source_id
            """
        )

    @staticmethod
    def _create_inventory_marts(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_inventory_health_latest AS
            WITH latest AS (
                SELECT max(snapshot_date) AS snapshot_date
                FROM fact_inventory_snapshot
            ),
            flow AS (
                SELECT
                    f.snapshot_date,
                    f.warehouse_id,
                    f.sku_id,
                    sum(CASE WHEN flow_type = 'sale' THEN quantity ELSE 0 END) AS sales_7d,
                    sum(CASE WHEN flow_type = 'inbound' THEN quantity ELSE 0 END) AS inbound_30d
                FROM fact_inventory_flow_daily f
                INNER JOIN latest l USING (snapshot_date)
                GROUP BY f.snapshot_date, f.warehouse_id, f.sku_id
            ),
            base AS (
                SELECT
                    i.*,
                    coalesce(f.sales_7d, 0) AS sales_7d,
                    coalesce(f.inbound_30d, 0) AS inbound_30d,
                    CASE WHEN f.sales_7d > 0
                         THEN i.available_qty / f.sales_7d END AS inventory_sales_ratio,
                    CASE WHEN f.sales_7d > 0
                         THEN i.available_qty * 7.0 / f.sales_7d END AS days_of_supply
                FROM fact_inventory_snapshot i
                INNER JOIN latest l USING (snapshot_date)
                LEFT JOIN flow f USING (snapshot_date, warehouse_id, sku_id)
            )
            SELECT *,
                available_qty < 0 AS negative_available,
                available_qty <= 0 AS out_of_stock,
                available_qty > 0 AND sales_7d = 0 AS no_recent_sales_with_stock,
                available_qty <= 0 OR (sales_7d > 0 AND days_of_supply <= 7)
                    AS stockout_risk,
                CASE
                    WHEN available_qty < 0 THEN 'negative_available'
                    WHEN available_qty = 0 THEN 'out_of_stock'
                    WHEN sales_7d > 0 AND days_of_supply <= 7 THEN 'critical_7d'
                    WHEN sales_7d > 0 AND days_of_supply <= 14 THEN 'low_14d'
                    WHEN available_qty > 0 AND sales_7d = 0 THEN 'no_recent_sales'
                    ELSE 'healthy_or_unclassified'
                END AS inventory_status
            FROM base
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_inventory_summary_latest AS
            SELECT
                snapshot_date,
                count(*) AS sku_warehouse_rows,
                count(DISTINCT warehouse_id) AS warehouses,
                count(DISTINCT sku_id) AS skus,
                sum(stock_qty) AS stock_qty,
                sum(available_qty) AS available_qty,
                sum(sales_7d) AS sales_7d,
                sum(inbound_30d) AS inbound_30d,
                count(*) FILTER (WHERE negative_available) AS negative_available_rows,
                count(*) FILTER (WHERE out_of_stock) AS out_of_stock_rows,
                count(*) FILTER (WHERE stockout_risk) AS stockout_risk_rows,
                count(*) FILTER (WHERE no_recent_sales_with_stock)
                    AS no_recent_sales_with_stock_rows
            FROM mart_inventory_health_latest
            GROUP BY snapshot_date
            """
        )

    @staticmethod
    def _create_financial_marts(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_financial_daily AS
            SELECT
                CAST(settled_at AS DATE) AS settlement_date,
                count(*) AS settlement_lines,
                count(DISTINCT order_anon_id) AS orders,
                sum(user_paid) AS user_paid,
                sum(income_total) AS income_total,
                sum(settlement_amount) AS settlement_amount,
                sum(platform_subsidy + other_platform_subsidy + creator_subsidy
                    + platform_payment_subsidy + monthly_payment_marketing_subsidy
                    + bank_subsidy) AS subsidy_total,
                sum(platform_service_fee) AS platform_service_fee,
                sum(creator_commission) AS creator_commission,
                sum(service_provider_commission) AS service_provider_commission,
                sum(channel_share) AS channel_share,
                sum(merchant_acquisition_service_fee) AS merchant_acquisition_service_fee,
                sum(offsite_promotion_fee) AS offsite_promotion_fee,
                sum(other_share) AS other_share,
                sum(expense_total) AS expense_total,
                sum(pre_settlement_refund) AS pre_settlement_refund,
                sum(commission_waived) AS commission_waived
            FROM fact_settlement
            GROUP BY CAST(settled_at AS DATE)
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE mart_financial_merchant_summary AS
            SELECT
                merchant_entity_id,
                min(CAST(settled_at AS DATE)) AS first_settlement_date,
                max(CAST(settled_at AS DATE)) AS last_settlement_date,
                count(*) AS settlement_lines,
                count(DISTINCT order_anon_id) AS orders,
                sum(user_paid) AS user_paid,
                sum(income_total) AS income_total,
                sum(settlement_amount) AS settlement_amount,
                sum(platform_service_fee) AS platform_service_fee,
                sum(creator_commission) AS creator_commission,
                sum(expense_total) AS expense_total
            FROM fact_settlement
            GROUP BY merchant_entity_id
            """
        )

    @staticmethod
    def _create_analysis_quality(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE analysis_quality AS
            SELECT 'channel_group_share_sum' AS check_id,
                   date::VARCHAR || '|' || shop_id AS entity_key,
                   sum(traffic_share) AS observed_value,
                   CASE WHEN sum(traffic_share) BETWEEN 0.98 AND 1.02
                        THEN 'pass'
                        WHEN sum(traffic_share) BETWEEN 0 AND 1.02 THEN 'info'
                        ELSE 'warn' END AS status
            FROM mart_channel_composition_daily
            GROUP BY date, shop_id
            UNION ALL
            SELECT 'product_capture_coverage',
                   date::VARCHAR || '|' || shop_id,
                   captured_product_coverage,
                   CASE WHEN captured_product_coverage IS NULL THEN 'info'
                        WHEN captured_product_coverage BETWEEN 0 AND 1.02 THEN 'info'
                        ELSE 'warn' END
            FROM mart_product_shop_coverage_daily
            """
        )

    def _export_marts(self, connection: duckdb.DuckDBPyConnection) -> None:
        assert self.curated_parquet_root is not None
        for table in (*MART_TABLES, "metric_registry", "analysis_quality"):
            target = str(self.curated_parquet_root / f"{table}.parquet").replace("'", "''")
            connection.execute(
                f"COPY (SELECT * FROM \"{table}\") TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )

    @staticmethod
    def _build_summary(
        connection: duckdb.DuckDBPyConnection,
        registry: MetricRegistry,
        mart_counts: dict[str, int],
    ) -> dict[str, Any]:
        inventory = _row_as_dict(
            connection,
            "SELECT * FROM mart_inventory_summary_latest",
        )
        quality_counts = _row_as_dict(
            connection,
            """
            SELECT
                count(*) AS checks,
                count(*) FILTER (WHERE status = 'pass') AS passed,
                count(*) FILTER (WHERE status = 'warn') AS warnings,
                count(*) FILTER (WHERE status = 'info') AS informational
            FROM analysis_quality
            """,
        )
        return {
            "schema_version": "1",
            "generated_at": datetime.now(UTC),
            "metric_registry": {
                "version": registry.config.version,
                "metric_count": len(registry.config.metrics),
                "primary_kpis": registry.config.framework.primary_kpis,
                "drivers": registry.config.framework.drivers,
                "guardrails": registry.config.framework.guardrails,
            },
            "mart_counts": mart_counts,
            "coverage": {
                "shop_observation_rows": _scalar_int(
                    connection, "SELECT count(*) FROM mart_shop_performance_daily"
                ),
                "shop_entities": _scalar_int(connection, "SELECT count(*) FROM mart_shop_summary"),
                "product_entities": _scalar_int(
                    connection, "SELECT count(*) FROM mart_product_summary"
                ),
                "search_term_entities": _scalar_int(
                    connection, "SELECT count(*) FROM mart_search_term_summary"
                ),
                "settlement_days": _scalar_int(
                    connection, "SELECT count(*) FROM mart_financial_daily"
                ),
            },
            "inventory_latest": inventory,
            "analysis_quality": quality_counts,
            "privacy": {
                "entity_ids": "stable_hmac_aliases",
                "raw_names_included": False,
                "external_api_used": False,
            },
            "limitations": [
                "Channel, product and search marts cover seven captured dates.",
                "Inventory product links remain candidate links until business confirmation.",
                "Settlement is analyzed by settlement date and cannot currently join to order extracts.",
                "Missing daily observations are not imputed as zero.",
            ],
        }


def _row_as_dict(connection: duckdb.DuckDBPyConnection, query: str) -> dict[str, Any] | None:
    cursor = connection.execute(query)
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [item[0] for item in cursor.description]
    return dict(zip(columns, row, strict=True))


def _scalar_int(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise ValueError(f"Scalar query returned no rows: {query}")
    return int(row[0])


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")
