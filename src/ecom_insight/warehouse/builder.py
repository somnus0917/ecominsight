from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
import structlog

from ecom_insight.config import AppSettings
from ecom_insight.ingestion import (
    ExternalOrdersAdapter,
    InventoryAdapter,
    LuopanSQLiteAdapter,
    OrdersAdapter,
    SettlementAdapter,
)
from ecom_insight.ingestion.base import AdapterOutput, Record, SourceAdapter
from ecom_insight.privacy import PrivacySanitizer, load_or_create_salt
from ecom_insight.warehouse.quality import evaluate_quality

LOGGER = structlog.get_logger(__name__)

STAGING_TO_FACT = {
    "stg_shop_daily": "fact_shop_daily",
    "stg_content_daily": "fact_content_daily",
    "stg_channel_daily": "fact_channel_daily",
    "stg_content_carrier_daily": "fact_content_carrier_daily",
    "stg_product_daily": "fact_product_daily",
    "stg_search_term_daily": "fact_search_term_daily",
    "stg_traffic_source_daily": "fact_traffic_source_daily",
    "stg_inventory_snapshot": "fact_inventory_snapshot",
    "stg_inventory_flow_daily": "fact_inventory_flow_daily",
    "stg_order_sanitized": "fact_order_sanitized",
    "stg_settlement": "fact_settlement",
    "stg_external_shop_daily": "fact_external_shop_daily",
}


@dataclass(frozen=True, slots=True)
class WarehouseBuildResult:
    database_path: Path
    parquet_root: Path
    quality_report_path: Path
    manifest_path: Path
    table_counts: dict[str, int]
    quality_status: str


class WarehouseBuilder:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def build(self) -> WarehouseBuildResult:
        self.settings.validate_expected_sources()
        self._validate_output_boundary()
        self.settings.output_root.mkdir(parents=True, exist_ok=True)

        configured_salt = (
            self.settings.hmac_salt.get_secret_value() if self.settings.hmac_salt else None
        )
        salt = load_or_create_salt(self.settings.salt_file, configured_salt)
        privacy = PrivacySanitizer(salt)
        adapters = self._adapters(privacy)

        all_tables: dict[str, list[Record]] = {}
        adapter_metadata: list[dict[str, Any]] = []
        for adapter in adapters:
            output = adapter.extract()
            self._merge_output(all_tables, output)
            adapter_metadata.append(
                {
                    "adapter": type(adapter).__name__,
                    "row_counts": output.row_counts,
                    "source_file_count": len(output.source_files),
                    "warnings": output.warnings,
                }
            )
            LOGGER.info(
                "adapter_complete",
                adapter=type(adapter).__name__,
                row_counts=output.row_counts,
                warning_count=len(output.warnings),
            )

        quality = evaluate_quality(all_tables)
        artifacts_root = self.settings.output_root / "artifacts"
        artifacts_root.mkdir(parents=True, exist_ok=True)
        quality_path = artifacts_root / "quality_report.json"
        quality_path.write_text(
            quality.model_dump_json(indent=2),
            encoding="utf-8",
        )
        if quality.failed:
            raise ValueError(f"Data quality checks failed; see {quality_path}")

        parquet_root = self.settings.output_root / "parquet"
        staging_root = parquet_root / "staging"
        curated_root = parquet_root / "curated"
        staging_root.mkdir(parents=True, exist_ok=True)
        curated_root.mkdir(parents=True, exist_ok=True)
        for table_name, records in all_tables.items():
            self._write_parquet(staging_root / f"{table_name}.parquet", records)

        database_path = self.settings.output_root / "ecom_insight.duckdb"
        with duckdb.connect(str(database_path)) as connection:
            self._build_duckdb(connection, staging_root, curated_root)

        table_counts = {name: len(rows) for name, rows in all_tables.items()}
        manifest = {
            "schema_version": "1",
            "built_at": datetime.now(UTC).isoformat(),
            "source_root_fingerprint": privacy.alias(
                "source_root", str(self.settings.source_root), "SourceRoot"
            ),
            "read_only_source": True,
            "external_api_enabled": self.settings.external_api_enabled,
            "adapters": adapter_metadata,
            "staging_table_counts": table_counts,
            "quality_status": quality.status,
            "database_file": database_path.name,
        }
        manifest_path = artifacts_root / "build_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        LOGGER.info(
            "warehouse_complete",
            database_path=str(database_path),
            quality_status=quality.status,
            table_count=len(table_counts),
        )
        return WarehouseBuildResult(
            database_path=database_path,
            parquet_root=parquet_root,
            quality_report_path=quality_path,
            manifest_path=manifest_path,
            table_counts=table_counts,
            quality_status=quality.status,
        )

    def _adapters(self, privacy: PrivacySanitizer) -> list[SourceAdapter]:
        return [
            LuopanSQLiteAdapter(self.settings.luopan_db(), privacy),
            InventoryAdapter(self.settings.inventory_root(), privacy),
            OrdersAdapter(self.settings.orders_root(), privacy),
            ExternalOrdersAdapter(self.settings.external_orders_file(), privacy),
            SettlementAdapter(self.settings.settlement_root(), privacy),
        ]

    def _validate_output_boundary(self) -> None:
        if self.settings.output_root.is_relative_to(self.settings.source_root):
            raise ValueError("Output root must not be inside the read-only source root")
        if self.settings.salt_file.is_relative_to(self.settings.source_root):
            raise ValueError("HMAC salt file must not be inside the source root")

    @staticmethod
    def _merge_output(all_tables: dict[str, list[Record]], output: AdapterOutput) -> None:
        for name, rows in output.tables.items():
            all_tables.setdefault(name, []).extend(rows)

    @staticmethod
    def _write_parquet(path: Path, records: list[Record]) -> None:
        if not records:
            raise ValueError(f"Refusing to write empty staging table: {path.stem}")
        frame = pl.DataFrame(records, infer_schema_length=None)
        frame.write_parquet(path, compression="zstd", statistics=True)

    def _build_duckdb(
        self,
        connection: duckdb.DuckDBPyConnection,
        staging_root: Path,
        curated_root: Path,
    ) -> None:
        connection.execute("SET TimeZone='Asia/Shanghai'")
        for staging_name, fact_name in STAGING_TO_FACT.items():
            parquet_path = staging_root / f"{staging_name}.parquet"
            escaped = str(parquet_path).replace("'", "''")
            connection.execute(
                f"CREATE OR REPLACE TABLE \"{staging_name}\" AS SELECT * FROM read_parquet('{escaped}')"
            )
            self._create_curated_fact(connection, staging_name, fact_name)

        self._create_dimensions(connection)
        self._create_bridges(connection)
        self._create_views(connection)

        export_tables = [
            *STAGING_TO_FACT.values(),
            "dim_date",
            "dim_platform",
            "dim_shop",
            "dim_product",
            "dim_sku",
            "dim_channel",
            "dim_content_type",
            "dim_warehouse",
            "bridge_product_sku",
        ]
        for table_name in export_tables:
            target = str(curated_root / f"{table_name}.parquet").replace("'", "''")
            connection.execute(
                f"COPY (SELECT * FROM \"{table_name}\") TO '{target}' "
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )

    @staticmethod
    def _create_curated_fact(
        connection: duckdb.DuckDBPyConnection, staging_name: str, fact_name: str
    ) -> None:
        columns = connection.execute(f'PRAGMA table_info("{staging_name}")').fetchall()
        expressions: list[str] = []
        for column in columns:
            name = str(column[1])
            quoted = name.replace('"', '""')
            if name.endswith("_fen"):
                target = name.removesuffix("_fen").replace('"', '""')
                expressions.append(
                    f'CAST(CASE WHEN "{quoted}" IS NULL THEN NULL '
                    f'ELSE CAST("{quoted}" AS DECIMAL(20,0)) * CAST(0.01 AS DECIMAL(4,2)) '
                    f'END AS DECIMAL(18,2)) AS "{target}"'
                )
            else:
                expressions.append(f'"{quoted}"')
        expressions.append("FALSE AS synthetic")
        expressions.append("NULL AS scenario_id")
        select_list = ",\n".join(expressions)
        connection.execute(
            f'CREATE OR REPLACE TABLE "{fact_name}" AS SELECT {select_list} FROM "{staging_name}"'
        )

    @staticmethod
    def _create_dimensions(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_date AS
            SELECT DISTINCT date
            FROM (
                SELECT date FROM fact_shop_daily
                UNION SELECT date FROM fact_product_daily
                UNION SELECT snapshot_date AS date FROM fact_inventory_snapshot
                UNION SELECT CAST(settled_at AS DATE) AS date FROM fact_settlement
            )
            WHERE date IS NOT NULL
            ORDER BY date
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_platform AS
            SELECT platform_id,
                   min(platform_type) AS platform_type
            FROM fact_shop_daily
            GROUP BY platform_id
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_shop AS
            SELECT shop_id,
                   min(shop_name_masked) AS shop_name_masked,
                   min(platform_id) AS platform_id,
                   min(date) AS first_seen_date,
                   max(date) AS last_seen_date
            FROM fact_shop_daily
            GROUP BY shop_id
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_product AS
            SELECT product_id, min(product_name_masked) AS product_name_masked,
                   'platform' AS source_system
            FROM fact_product_daily GROUP BY product_id
            UNION ALL
            SELECT product_id, min(product_name_masked), 'order'
            FROM fact_order_sanitized GROUP BY product_id
            UNION ALL
            SELECT product_id, min(product_name_masked), 'settlement'
            FROM fact_settlement GROUP BY product_id
            UNION ALL
            SELECT goods_id, min(goods_name_masked), 'wms'
            FROM fact_inventory_snapshot GROUP BY goods_id
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_sku AS
            SELECT sku_id, min(sku_name_masked) AS sku_name_masked,
                   'wms' AS source_system
            FROM fact_inventory_snapshot GROUP BY sku_id
            UNION ALL
            SELECT sku_id, min(sku_name_masked), 'order'
            FROM fact_order_sanitized
            WHERE sku_id <> ''
            GROUP BY sku_id
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_channel AS
            SELECT channel_id,
                   min(channel_group) AS channel_group,
                   min(channel_level) AS channel_level,
                   min(parent_channel_id) AS parent_channel_id
            FROM fact_channel_daily GROUP BY channel_id
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_content_type AS
            SELECT DISTINCT content_type FROM (
                SELECT content_type FROM fact_content_daily
                UNION SELECT content_type FROM fact_content_carrier_daily
            )
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_warehouse AS
            SELECT warehouse_id, min(warehouse_name_masked) AS warehouse_name_masked
            FROM fact_inventory_snapshot GROUP BY warehouse_id
            """
        )

    @staticmethod
    def _create_bridges(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE bridge_product_sku AS
            SELECT DISTINCT
                o.product_id,
                o.sku_id,
                'standard_code_exact' AS link_method,
                'candidate' AS link_status,
                CAST(0.70 AS DOUBLE) AS confidence,
                'Observed merchant SKU code equals WMS spec code; business confirmation required'
                    AS evidence
            FROM fact_order_sanitized o
            INNER JOIN (SELECT DISTINCT sku_id FROM fact_inventory_snapshot) i USING (sku_id)
            WHERE o.sku_id <> ''
            """
        )

    @staticmethod
    def _create_views(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE VIEW vw_shop_daily_metrics AS
            SELECT *,
                   paid_amount / NULLIF(paid_users, 0) AS avg_order_value_calculated,
                   click_users / NULLIF(exposure_users, 0) AS exposure_click_rate_calculated,
                   paid_users / NULLIF(click_users, 0) AS click_conversion_rate_calculated,
                   paid_amount / NULLIF(ad_spend, 0) AS roas
            FROM fact_shop_daily
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW vw_latest_inventory AS
            SELECT *
            FROM fact_inventory_snapshot
            QUALIFY snapshot_date = max(snapshot_date) OVER ()
            """
        )
