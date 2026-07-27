from __future__ import annotations

import csv
from pathlib import Path

from ecom_insight.ingestion.orders import OrdersAdapter
from ecom_insight.privacy import PrivacySanitizer

ORDER_HEADER = [
    "order_no",
    "order_time",
    "header_extra",
    "product_name",
    "sku_spec",
    "merchant_sku_code",
    "author",
    "item_order_id",
    "product_tags",
    "price_quantity",
    "aftersale_status",
    "order_status",
    "merchant_income",
    "receiver_name",
    "receiver_phone",
    "receiver_address",
    "operations",
]


def _write_order(path: Path, order_no: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ORDER_HEADER)
        writer.writeheader()
        writer.writerow(
            {
                "order_no": order_no,
                "order_time": "2026-01-01 12:00:00",
                "product_name": "合成商品",
                "sku_spec": "合成规格",
                "merchant_sku_code": "SYN-SKU-1",
                "author": "合成达人",
                "item_order_id": f"{order_no}-item",
                "product_tags": "synthetic",
                "price_quantity": "¥99.00 x 1",
                "aftersale_status": "none",
                "order_status": "paid",
                "merchant_income": "¥90.00",
                "receiver_name": "测试用户",
                "receiver_phone": "13800138000",
                "receiver_address": "测试省测试市测试路1号",
            }
        )


def test_only_date_directories_are_authoritative_and_pii_is_removed(tmp_path: Path) -> None:
    root = tmp_path / "orders"
    _write_order(root / "2026-01-01" / "orders.csv", "synthetic-1")
    _write_order(root / "2026-01-01" / "douyin_orders_2026-01-01.csv", "synthetic-2")
    _write_order(root / "test_2026-01-01" / "douyin_orders_test.csv", "synthetic-3")

    output = OrdersAdapter(root, PrivacySanitizer(b"x" * 32)).extract()
    rows = output.tables["stg_order_sanitized"]

    assert len(rows) == 1
    assert rows[0]["order_anon_id"].startswith("Order_")
    assert rows[0]["sku_id"].startswith("SKU_")
    assert not {"receiver_name", "receiver_phone", "receiver_address"}.intersection(rows[0])
