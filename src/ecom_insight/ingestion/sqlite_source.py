from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ecom_insight.ingestion.base import AdapterOutput, Record
from ecom_insight.privacy import PrivacySanitizer
from ecom_insight.utils.parsing import fen_to_yuan_fen, parse_date, parse_datetime

SHOP_AMOUNT_FIELDS = {
    "income_amt": "gmv_fen",
    "pay_amt": "paid_amount_fen",
    "per_usr_pay_amt": "avg_order_value_source_fen",
    "per_item_pay_amt": "avg_item_price_source_fen",
    "pay_amt_per_k_show": "gpm_source_fen",
    "refund_amt_pay_time": "refund_amount_by_pay_time_fen",
    "deal_refund_amt_pay_time": "deal_refund_amount_by_pay_time_fen",
    "refund_amt": "refund_amount_by_refund_time_fen",
    "rfndsuc_amt": "successful_refund_amount_fen",
    "settlement_amt_pay_time": "settlement_amount_by_pay_time_fen",
    "settlement_amt_7d": "settlement_amount_7d_fen",
    "settlement_amt_14d": "settlement_amount_14d_fen",
    "expense_amt": "expense_amount_fen",
    "ad_cost_amt": "ad_spend_fen",
    "platform_subsidy_amt": "platform_subsidy_fen",
    "talent_subsidy_amt": "creator_subsidy_fen",
    "platform_commission_amt": "platform_commission_fen",
    "talent_commission_amt": "creator_commission_fen",
}

SHOP_COUNT_FIELDS = {
    "pay_cnt": "paid_orders",
    "pay_item_cnt": "paid_items",
    "pay_ucnt": "paid_users",
    "product_show_ucnt": "exposure_users",
    "product_show_cnt": "exposure_count",
    "product_click_ucnt": "click_users",
    "product_click_cnt": "click_count",
    "refund_order_cnt_pay_time": "refund_orders_by_pay_time",
    "refund_order_cnt": "refund_orders_by_refund_time",
}

SHOP_RATIO_FIELDS = {
    "product_show_click_ucnt_ratio": "exposure_click_rate_users",
    "product_click_pay_ucnt_ratio": "click_conversion_rate_users",
    "product_show_pay_ucnt_ratio": "exposure_conversion_rate_users",
    "product_show_click_cnt_ratio": "exposure_click_rate_count",
    "product_click_pay_cnt_ratio": "click_conversion_rate_count",
    "product_show_pay_cnt_ratio": "exposure_conversion_rate_count",
    "refund_amt_rate": "refund_rate_by_pay_time",
}

CONTENT_TYPES = {
    "live": "live",
    "product_card": "product_card",
    "video": "short_video",
    "artc_video": "article_or_video",
    "other_content": "other",
}


class LuopanSQLiteAdapter:
    """Read only the four analytical tables in luopan.db."""

    def __init__(self, database: Path, privacy: PrivacySanitizer) -> None:
        self.database = database.resolve()
        self.privacy = privacy

    def _connect(self) -> sqlite3.Connection:
        if not self.database.is_file():
            raise FileNotFoundError(self.database)
        return sqlite3.connect(f"file:{self.database}?mode=ro", uri=True)

    def extract(self) -> AdapterOutput:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            shop_daily, content_daily = self._extract_shop_daily(connection)
            channel_daily, carriers = self._extract_channel_daily(connection)
            product_daily = self._extract_product_daily(connection)
            search_terms, traffic_sources = self._extract_search_daily(connection)

        tables = {
            "stg_shop_daily": shop_daily,
            "stg_content_daily": content_daily,
            "stg_channel_daily": channel_daily,
            "stg_content_carrier_daily": carriers,
            "stg_product_daily": product_daily,
            "stg_search_term_daily": search_terms,
            "stg_traffic_source_daily": traffic_sources,
        }
        return AdapterOutput(tables=tables, source_files=[self.database])

    def _extract_shop_daily(
        self, connection: sqlite3.Connection
    ) -> tuple[list[Record], list[Record]]:
        rows = connection.execute(
            """
            SELECT shop_id, date, captured_at, metrics_json, content_json,
                   source, source_key, source_label
            FROM operation_records
            ORDER BY date, shop_id
            """
        )
        facts: list[Record] = []
        content_facts: list[Record] = []
        for row in rows:
            metrics = _json_object(row["metrics_json"])
            content = _json_object(row["content_json"])
            raw_shop_id = str(row["shop_id"])
            shop_id = self.privacy.shop_id(raw_shop_id)
            source = str(row["source"])
            source_label = str(row["source_label"] or "")
            platform_seed = "douyin" if source == "daily_json" else source_label
            platform_id = self.privacy.masked_label("platform", platform_seed, "Platform")
            business_date = parse_date(row["date"])
            fact: Record = {
                "date": business_date,
                "platform_id": platform_id,
                "platform_type": "douyin" if source == "daily_json" else "external",
                "shop_id": shop_id,
                "shop_name_masked": shop_id,
                "source_system": source,
                "source_record_id": self.privacy.alias(
                    "source_record", f"{source}|{raw_shop_id}|{row['date']}", "Record"
                ),
                "captured_at": parse_datetime(row["captured_at"]),
                "present_metrics": "|".join(sorted(metrics)),
            }
            for source_key, target_key in SHOP_AMOUNT_FIELDS.items():
                fact[target_key] = fen_to_yuan_fen(metrics.get(source_key))
            for source_key, target_key in SHOP_COUNT_FIELDS.items():
                fact[target_key] = _optional_int(metrics.get(source_key))
            for source_key, target_key in SHOP_RATIO_FIELDS.items():
                fact[target_key] = _optional_float(metrics.get(source_key))
            fact["merchant_experience_score"] = _optional_float(metrics.get("service_score"))
            facts.append(fact)

            for raw_content_type, content_type in CONTENT_TYPES.items():
                if raw_content_type not in content:
                    continue
                content_facts.append(
                    {
                        "date": business_date,
                        "platform_id": platform_id,
                        "shop_id": shop_id,
                        "content_type": content_type,
                        "paid_amount_fen": fen_to_yuan_fen(content.get(raw_content_type)),
                        "field_present": True,
                        "source_system": source,
                    }
                )
        return facts, content_facts

    def _extract_channel_daily(
        self, connection: sqlite3.Connection
    ) -> tuple[list[Record], list[Record]]:
        rows = connection.execute(
            "SELECT shop_id, date, captured_at, traffic_json FROM channel_daily ORDER BY date, shop_id"
        )
        channel_facts: list[Record] = []
        carrier_facts: list[Record] = []
        for row in rows:
            raw_shop_id = str(row["shop_id"])
            shop_id = self.privacy.shop_id(raw_shop_id)
            business_date = parse_date(row["date"])
            traffic = _json_object(row["traffic_json"])
            source_metric = traffic.get("source_metric")

            for item in _json_list(traffic.get("sources")):
                raw_code = str(item.get("code", ""))
                channel_facts.append(
                    {
                        "date": business_date,
                        "shop_id": shop_id,
                        "channel_id": self.privacy.alias("channel", raw_code, "Channel"),
                        "channel_group": str(item.get("group", "")),
                        "channel_level": "source",
                        "parent_channel_id": self.privacy.alias(
                            "channel", str(item.get("parent") or ""), "Channel"
                        ),
                        "source_metric": source_metric,
                        "metric_value": _optional_float(item.get("value")),
                        "traffic_share": _optional_float(item.get("source_ratio")),
                    }
                )

            groups = _json_object(traffic.get("groups"))
            for group_name, group_value in groups.items():
                group_payload = _json_object(group_value)
                channel_facts.append(
                    {
                        "date": business_date,
                        "shop_id": shop_id,
                        "channel_id": self.privacy.alias(
                            "channel_group", group_name, "ChannelGroup"
                        ),
                        "channel_group": group_name,
                        "channel_level": "group",
                        "parent_channel_id": "",
                        "source_metric": source_metric,
                        "metric_value": _optional_float(group_payload.get("value")),
                        "traffic_share": _optional_float(group_payload.get("ratio")),
                    }
                )

            carriers = _json_object(traffic.get("carriers"))
            for carrier_type, carrier_value in carriers.items():
                payload = _json_object(carrier_value)
                carrier_facts.append(
                    {
                        "date": business_date,
                        "shop_id": shop_id,
                        "content_type": carrier_type,
                        "paid_amount_fen": fen_to_yuan_fen(payload.get("pay_amt")),
                        "refund_rate": _optional_float(payload.get("refund_rate")),
                        "exposure_conversion_rate": _optional_float(
                            payload.get("show_pay_ucnt_rate")
                        ),
                        "exposure_users": _optional_int(payload.get("show_ucnt")),
                        "exposure_users_benchmark": _optional_float(
                            payload.get("show_ucnt_benchmark")
                        ),
                        "exposure_users_change_rate": _optional_float(
                            payload.get("show_ucnt_change")
                        ),
                        "watch_users": _optional_int(payload.get("watch_ucnt")),
                        "watch_users_benchmark": _optional_float(
                            payload.get("watch_ucnt_benchmark")
                        ),
                        "watch_users_change_rate": _optional_float(
                            payload.get("watch_ucnt_change")
                        ),
                        "gpm_fen": fen_to_yuan_fen(payload.get("gpm")),
                        "gpm_benchmark_fen": fen_to_yuan_fen(payload.get("gpm_benchmark")),
                    }
                )
        return channel_facts, carrier_facts

    def _extract_product_daily(self, connection: sqlite3.Connection) -> list[Record]:
        rows = connection.execute(
            """
            SELECT shop_id, date, product_id, payload_json
            FROM channel_product_daily
            ORDER BY date, shop_id, product_id
            """
        )
        facts: list[Record] = []
        for row in rows:
            payload = _json_object(row["payload_json"])
            raw_product_id = str(row["product_id"])
            facts.append(
                {
                    "date": parse_date(row["date"]),
                    "shop_id": self.privacy.shop_id(str(row["shop_id"])),
                    "product_id": self.privacy.product_id(raw_product_id),
                    "product_name_masked": self.privacy.masked_label(
                        "product_name", str(payload.get("product_name", "")), "ProductName"
                    ),
                    "has_product_image": bool(payload.get("product_image")),
                    "price_fen": fen_to_yuan_fen(payload.get("product_price")),
                    "paid_amount_fen": fen_to_yuan_fen(payload.get("pay_amt")),
                    "paid_orders": _optional_int(payload.get("pay_cnt")),
                    "paid_users": _optional_int(payload.get("pay_ucnt")),
                    "exposure_users": _optional_int(payload.get("show_ucnt")),
                    "click_users": _optional_int(payload.get("click_ucnt")),
                    "click_rate": _optional_float(payload.get("click_rate")),
                    "click_conversion_rate": _optional_float(payload.get("click_pay_rate")),
                    "paid_amount_change_rate": _optional_float(payload.get("pay_amt_change")),
                    "exposure_change_rate": _optional_float(payload.get("show_ucnt_change")),
                    "first_listed_at": parse_datetime(payload.get("first_onshelf_date")),
                }
            )
        return facts

    def _extract_search_daily(
        self, connection: sqlite3.Connection
    ) -> tuple[list[Record], list[Record]]:
        rows = connection.execute(
            """
            SELECT shop_id, date, kind, row_key, payload_json
            FROM channel_search_daily
            ORDER BY date, shop_id, kind, row_key
            """
        )
        term_facts: list[Record] = []
        source_facts: list[Record] = []
        for row in rows:
            payload = _json_object(row["payload_json"])
            shop_id = self.privacy.shop_id(str(row["shop_id"]))
            business_date = parse_date(row["date"])
            kind = str(row["kind"])
            if kind in {"industry_term", "shop_term"}:
                raw_word = str(payload.get("word", ""))
                term_facts.append(
                    {
                        "date": business_date,
                        "shop_id": shop_id,
                        "term_kind": kind,
                        "term_id": self.privacy.alias("search_term", raw_word, "Term"),
                        "rank": _optional_int(payload.get("rank")),
                        "paid_amount_fen": fen_to_yuan_fen(payload.get("pay_amt")),
                        "paid_amount_change_rate": _optional_float(payload.get("pay_amt_change")),
                        "paid_amount_lower_fen": fen_to_yuan_fen(payload.get("pay_amt_lower")),
                        "paid_amount_upper_fen": fen_to_yuan_fen(payload.get("pay_amt_upper")),
                        "exposure_users": _optional_int(payload.get("show_ucnt")),
                        "exposure_change_rate": _optional_float(payload.get("show_ucnt_change")),
                        "exposure_lower": _optional_int(payload.get("show_ucnt_lower")),
                        "exposure_upper": _optional_int(payload.get("show_ucnt_upper")),
                    }
                )
            elif kind == "source":
                raw_name = str(payload.get("name", ""))
                source_facts.append(
                    {
                        "date": business_date,
                        "shop_id": shop_id,
                        "traffic_source_id": self.privacy.alias(
                            "traffic_source", raw_name, "TrafficSource"
                        ),
                        "paid_amount_fen": fen_to_yuan_fen(payload.get("pay_amt")),
                        "paid_amount_change_rate": _optional_float(payload.get("pay_amt_change")),
                        "paid_amount_benchmark_fen": fen_to_yuan_fen(
                            payload.get("pay_amt_benchmark")
                        ),
                        "exposure_users": _optional_int(payload.get("show_ucnt")),
                        "exposure_change_rate": _optional_float(payload.get("show_ucnt_change")),
                        "exposure_benchmark": _optional_float(payload.get("show_ucnt_benchmark")),
                    }
                )
        return term_facts, source_facts


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def _json_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Expected a JSON array")
    return [item for item in value if isinstance(item, dict)]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
