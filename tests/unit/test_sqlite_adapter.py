from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ecom_insight.ingestion.sqlite_source import LuopanSQLiteAdapter
from ecom_insight.privacy import PrivacySanitizer


def _create_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE operation_records (
            shop_id TEXT, date TEXT, captured_at TEXT, metrics_json TEXT,
            content_json TEXT, source TEXT, source_key TEXT, source_label TEXT
        );
        CREATE TABLE channel_daily (
            shop_id TEXT, date TEXT, captured_at TEXT, traffic_json TEXT
        );
        CREATE TABLE channel_product_daily (
            shop_id TEXT, date TEXT, product_id TEXT, payload_json TEXT
        );
        CREATE TABLE channel_search_daily (
            shop_id TEXT, date TEXT, kind TEXT, row_key TEXT, payload_json TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO operation_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "shop-raw",
            "2026-01-01",
            "2026-01-02 00:00:00",
            json.dumps(
                {
                    "pay_amt": 12345,
                    "income_amt": 13000,
                    "pay_cnt": 1,
                    "pay_ucnt": 1,
                    "product_show_ucnt": 100,
                    "product_click_ucnt": 10,
                    "product_show_click_ucnt_ratio": 0.1,
                    "product_click_pay_ucnt_ratio": 0.1,
                    "refund_amt_rate": 0,
                }
            ),
            json.dumps({"live": 12345}),
            "daily_json",
            None,
            None,
        ),
    )
    connection.execute(
        "INSERT INTO channel_daily VALUES (?, ?, ?, ?)",
        (
            "shop-raw",
            "2026-01-01",
            "2026-01-02 00:00:00",
            json.dumps(
                {
                    "source_metric": "show_ucnt",
                    "sources": [
                        {
                            "code": "search",
                            "group": "organic_search",
                            "parent": None,
                            "value": 100,
                            "source_ratio": 1.0,
                        }
                    ],
                    "groups": {"organic_search": {"value": 100, "ratio": 1.0}},
                    "carriers": {"all": {"pay_amt": 12345, "show_ucnt": 100}},
                }
            ),
        ),
    )
    connection.execute(
        "INSERT INTO channel_product_daily VALUES (?, ?, ?, ?)",
        (
            "shop-raw",
            "2026-01-01",
            "product-raw",
            json.dumps(
                {
                    "product_name": "合成商品",
                    "product_image": "https://example.invalid/image.png",
                    "product_price": 12345,
                    "pay_amt": 12345,
                    "pay_ucnt": 1,
                    "show_ucnt": 100,
                }
            ),
        ),
    )
    connection.execute(
        "INSERT INTO channel_search_daily VALUES (?, ?, ?, ?, ?)",
        (
            "shop-raw",
            "2026-01-01",
            "shop_term",
            "synthetic-key",
            json.dumps({"word": "合成词", "rank": 1, "pay_amt": 12345, "show_ucnt": 100}),
        ),
    )
    connection.commit()
    connection.close()


def test_sqlite_adapter_is_read_only_and_masks_entities(tmp_path: Path) -> None:
    database = tmp_path / "luopan.db"
    _create_database(database)

    output = LuopanSQLiteAdapter(database, PrivacySanitizer(b"x" * 32)).extract()
    shop = output.tables["stg_shop_daily"][0]
    product = output.tables["stg_product_daily"][0]

    assert shop["paid_amount_fen"] == 12345
    assert shop["shop_id"].startswith("Shop_")
    assert "shop-raw" not in str(output.tables)
    assert product["product_name_masked"].startswith("ProductName_")
