from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from ecom_insight.api.schemas import KpiValue, OverviewResponse, TrendPoint


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date,)):
        return value.isoformat()
    return value


class AnalyticsRepository:
    """Fixed-query read-only access to curated and analytical DuckDB objects."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()

    def exists(self) -> bool:
        return self.database_path.is_file()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if not self.exists():
            raise FileNotFoundError(self.database_path)
        return duckdb.connect(str(self.database_path), read_only=True)

    @staticmethod
    def _records(
        connection: duckdb.DuckDBPyConnection,
        sql: str,
        parameters: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        cursor = connection.execute(sql, parameters or [])
        columns = [item[0] for item in cursor.description]
        return [
            {
                column: _json_value(value)
                for column, value in zip(columns, row, strict=True)
            }
            for row in cursor.fetchall()
        ]

    @staticmethod
    def _date_clause(
        *,
        column: str,
        date_from: date | None,
        date_to: date | None,
        shop_id: str | None = None,
    ) -> tuple[str, list[Any]]:
        clauses = ["1 = 1"]
        parameters: list[Any] = []
        if date_from is not None:
            clauses.append(f"{column} >= ?")
            parameters.append(date_from)
        if date_to is not None:
            clauses.append(f"{column} <= ?")
            parameters.append(date_to)
        if shop_id is not None:
            clauses.append("shop_id = ?")
            parameters.append(shop_id)
        return " AND ".join(clauses), parameters

    def data_updated_at(self) -> date | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT max(date) FROM mart_shop_performance_daily"
            ).fetchone()
        return row[0] if row and isinstance(row[0], date) else None

    def overview(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        shop_id: str | None,
    ) -> OverviewResponse:
        where, parameters = self._date_clause(
            column="date",
            date_from=date_from,
            date_to=date_to,
            shop_id=shop_id,
        )
        with self._connect() as connection:
            totals = connection.execute(
                f"""
                SELECT
                    coalesce(sum(paid_amount), 0),
                    coalesce(sum(paid_orders), 0),
                    coalesce(sum(refund_amount_by_pay_time), 0),
                    coalesce(sum(ad_spend), 0),
                    coalesce(sum(settlement_amount_by_pay_time), 0)
                FROM mart_shop_performance_daily
                WHERE {where}
                """,
                parameters,
            ).fetchone()
            anomaly_row = connection.execute(
                f"""
                SELECT count(DISTINCT attribution_id)
                FROM fact_attribution
                WHERE {where.replace("shop_id", "entity_id")}
                """,
                parameters,
            ).fetchone()
            anomaly_total = int(anomaly_row[0]) if anomaly_row is not None else 0
            trend_rows = connection.execute(
                f"""
                SELECT
                    date,
                    coalesce(sum(paid_amount), 0) AS paid_amount,
                    coalesce(sum(paid_orders), 0) AS paid_orders,
                    coalesce(sum(refund_amount_by_pay_time), 0) AS refund_amount,
                    coalesce(sum(ad_spend), 0) AS ad_spend,
                    coalesce(sum(settlement_amount_by_pay_time), 0) AS settlement_amount
                FROM mart_shop_performance_daily
                WHERE {where}
                GROUP BY date
                ORDER BY date
                """,
                parameters,
            ).fetchall()
            shop_rows = self._records(
                connection,
                f"""
                SELECT
                    shop_id,
                    max(platform_type) AS platform,
                    sum(paid_amount) AS paid_amount,
                    sum(paid_orders) AS paid_orders,
                    max(date) AS latest_date
                FROM mart_shop_performance_daily
                WHERE {where}
                GROUP BY shop_id
                ORDER BY paid_amount DESC
                """,
                parameters,
            )
        assert totals is not None
        return OverviewResponse(
            data_updated_at=self.data_updated_at(),
            kpis=[
                KpiValue(code="paid_amount", label="支付金额", value=float(totals[0]), unit="CNY"),
                KpiValue(code="paid_orders", label="支付订单", value=float(totals[1]), unit="orders"),
                KpiValue(code="refund_amount", label="退款金额", value=float(totals[2]), unit="CNY"),
                KpiValue(code="ad_spend", label="广告消耗", value=float(totals[3]), unit="CNY"),
                KpiValue(
                    code="settlement_amount",
                    label="日报结算金额",
                    value=float(totals[4]),
                    unit="CNY",
                ),
                KpiValue(
                    code="anomaly_count",
                    label="异常事件",
                    value=float(anomaly_total),
                    unit="events",
                ),
            ],
            trend=[
                TrendPoint(
                    date=row[0],
                    paid_amount=float(row[1]),
                    paid_orders=int(row[2]),
                    refund_amount=float(row[3]),
                    ad_spend=float(row[4]),
                    settlement_amount=float(row[5]),
                )
                for row in trend_rows
            ],
            shops=shop_rows,
        )

    def shops(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return self._records(
                connection,
                """
                SELECT
                    shop_id,
                    platform_type AS platform,
                    min(date) AS first_date,
                    max(date) AS last_date,
                    count(*) AS observation_days,
                    sum(paid_amount) AS paid_amount
                FROM mart_shop_performance_daily
                GROUP BY shop_id, platform_type
                ORDER BY paid_amount DESC
                """,
            )

    def shop_detail(
        self,
        shop_id: str,
        *,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        where, parameters = self._date_clause(
            column="date",
            date_from=date_from,
            date_to=date_to,
            shop_id=shop_id,
        )
        with self._connect() as connection:
            trend = self._records(
                connection,
                f"""
                SELECT
                    date, paid_amount, paid_orders, exposure_users, click_users,
                    exposure_click_rate, click_conversion_rate, avg_order_value,
                    refund_rate_by_pay_time, ad_spend, roas,
                    settlement_amount_by_pay_time, merchant_experience_score
                FROM mart_shop_performance_daily
                WHERE {where}
                ORDER BY date
                """,
                parameters,
            )
            carriers = self._records(
                connection,
                """
                SELECT *
                FROM mart_content_carrier_summary
                WHERE shop_id = ?
                ORDER BY paid_amount DESC NULLS LAST
                """,
                [shop_id],
            )
            channels = self._records(
                connection,
                """
                SELECT
                    channel_group,
                    sum(metric_value) AS metric_value,
                    avg(traffic_share) AS traffic_share
                FROM mart_channel_composition_daily
                WHERE shop_id = ?
                GROUP BY channel_group
                ORDER BY metric_value DESC
                """,
                [shop_id],
            )
        if not trend:
            raise KeyError(shop_id)
        return {"shop_id": shop_id, "trend": trend, "carriers": carriers, "channels": channels}

    def products(self, *, shop_id: str | None, limit: int) -> list[dict[str, Any]]:
        clause = "WHERE shop_id = ?" if shop_id else ""
        parameters: list[Any] = [shop_id] if shop_id else []
        parameters.append(limit)
        with self._connect() as connection:
            return self._records(
                connection,
                f"""
                SELECT *
                FROM mart_product_summary
                {clause}
                ORDER BY paid_amount DESC NULLS LAST
                LIMIT ?
                """,
                parameters,
            )

    def search_terms(self, *, shop_id: str | None, limit: int) -> list[dict[str, Any]]:
        clause = "WHERE shop_id = ?" if shop_id else ""
        parameters: list[Any] = [shop_id] if shop_id else []
        parameters.append(limit)
        with self._connect() as connection:
            return self._records(
                connection,
                f"""
                SELECT *
                FROM mart_search_term_summary
                {clause}
                ORDER BY paid_amount DESC NULLS LAST, latest_rank ASC NULLS LAST
                LIMIT ?
                """,
                parameters,
            )

    def inventory(self, *, status: str | None, limit: int) -> list[dict[str, Any]]:
        clause = "WHERE inventory_status = ?" if status else ""
        parameters: list[Any] = [status] if status else []
        parameters.append(limit)
        with self._connect() as connection:
            return self._records(
                connection,
                f"""
                SELECT
                    snapshot_date,
                    warehouse_id,
                    warehouse_name_masked,
                    brand_id,
                    brand_name_masked,
                    goods_id,
                    goods_name_masked,
                    sku_id,
                    sku_name_masked,
                    stock_qty,
                    available_qty,
                    locked_qty,
                    sales_7d,
                    inbound_30d,
                    inventory_sales_ratio,
                    days_of_supply,
                    negative_available,
                    out_of_stock,
                    no_recent_sales_with_stock,
                    stockout_risk,
                    inventory_status
                FROM mart_inventory_health_latest
                {clause}
                ORDER BY stockout_risk DESC, days_of_supply DESC NULLS LAST
                LIMIT ?
                """,
                parameters,
            )

    def finance(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return self._records(
                connection,
                """
                SELECT *
                FROM mart_financial_daily
                ORDER BY settlement_date
                """,
            )

    def anomalies(
        self,
        *,
        metric: str | None,
        severity: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses = ["candidate_rank = 1"]
        parameters: list[Any] = []
        if metric:
            clauses.append("target_metric = ?")
            parameters.append(metric)
        if severity:
            clauses.append("severity = ?")
            parameters.append(severity)
        if status:
            clauses.append("evidence_status = ?")
            parameters.append(status)
        where = " AND ".join(clauses)
        offset = (page - 1) * page_size
        with self._connect() as connection:
            base = """
                WITH ranked AS (
                    SELECT *,
                        row_number() OVER (
                            PARTITION BY attribution_id
                            ORDER BY confidence DESC, rule_id
                        ) AS candidate_rank
                    FROM fact_attribution
                )
            """
            total_row = connection.execute(
                f"{base} SELECT count(*) FROM ranked WHERE {where}",
                parameters,
            ).fetchone()
            total = int(total_row[0]) if total_row is not None else 0
            items = self._records(
                connection,
                f"""
                {base}
                SELECT
                    attribution_id, entity_id, date, target_metric,
                    anomaly_score, severity, rule_id, cause, evidence_status,
                    confidence, detector_names_json
                FROM ranked
                WHERE {where}
                ORDER BY date DESC, anomaly_score DESC
                LIMIT ? OFFSET ?
                """,
                [*parameters, page_size, offset],
            )
        for item in items:
            item["detector_names"] = json.loads(str(item.pop("detector_names_json")))
        return items, total

    def anomaly_exists(self, attribution_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT count(*) FROM fact_attribution WHERE attribution_id = ?",
                [attribution_id],
            ).fetchone()
        return bool(row and int(row[0]) > 0)

    def anomaly_detail(self, attribution_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            candidates = self._records(
                connection,
                """
                SELECT
                    attribution_id, entity_id, date, target_metric,
                    anomaly_score, severity, rule_id, cause_code, cause,
                    evidence_status, confidence, explanation,
                    missing_information_json, decomposition_json
                FROM fact_attribution
                WHERE attribution_id = ?
                ORDER BY confidence DESC, rule_id
                """,
                [attribution_id],
            )
            if not candidates:
                raise KeyError(attribution_id)
            evidence = self._records(
                connection,
                """
                SELECT *
                FROM fact_attribution_evidence
                WHERE attribution_id = ?
                ORDER BY evidence_role, metric
                """,
                [attribution_id],
            )
            report_rows = self._records(
                connection,
                """
                SELECT report_json, validation_json
                FROM fact_attribution_report
                WHERE attribution_id = ?
                LIMIT 1
                """,
                [attribution_id],
            )
            event_date = date.fromisoformat(str(candidates[0]["date"]))
            trend = self._records(
                connection,
                """
                SELECT
                    date, paid_amount, exposure_users, exposure_click_rate,
                    click_conversion_rate, avg_order_value,
                    refund_rate_by_pay_time, ad_spend, roas,
                    settlement_amount_by_pay_time
                FROM mart_shop_performance_daily
                WHERE shop_id = ? AND date BETWEEN ? AND ?
                ORDER BY date
                """,
                [
                    candidates[0]["entity_id"],
                    event_date - timedelta(days=14),
                    event_date + timedelta(days=7),
                ],
            )
        for candidate in candidates:
            for key in ("missing_information_json", "decomposition_json"):
                if candidate[key] is not None:
                    candidate[key.removesuffix("_json")] = json.loads(
                        str(candidate.pop(key))
                    )
                else:
                    candidate.pop(key)
        report = None
        validation = None
        if report_rows:
            report = json.loads(str(report_rows[0]["report_json"]))
            validation = json.loads(str(report_rows[0]["validation_json"]))
        return {
            "event": candidates[0],
            "candidates": candidates,
            "evidence": evidence,
            "trend": trend,
            "report": report,
            "validation": validation,
        }
