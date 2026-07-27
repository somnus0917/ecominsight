from __future__ import annotations

import stat
from pathlib import Path

import pytest

from ecom_insight.models import SanitizedOrderRecord
from ecom_insight.privacy import PrivacySanitizer, load_or_create_salt


def test_stable_aliases_are_namespaced() -> None:
    sanitizer = PrivacySanitizer(b"x" * 32)

    assert sanitizer.shop_id("same") == sanitizer.shop_id("same")
    assert sanitizer.shop_id("same") != sanitizer.product_id("same")
    assert "same" not in sanitizer.shop_id("same")


def test_order_pii_is_deleted_before_return() -> None:
    sanitizer = PrivacySanitizer(b"x" * 32)
    sanitized = sanitizer.sanitize_order_identifiers(
        {
            "order_no": "synthetic-order-001",
            "item_order_id": "synthetic-item-001",
            "receiver_name": "测试用户",
            "receiver_phone": "13800138000",
            "receiver_address": "测试地址",
            "order_status": "paid",
        }
    )

    assert "receiver_name" not in sanitized
    assert "receiver_phone" not in sanitized
    assert "receiver_address" not in sanitized
    assert "order_no" not in sanitized
    assert "item_order_id" not in sanitized
    assert sanitized["order_anon_id"].startswith("Order_")


def test_sensitive_scan_rejects_phone_and_auth_header() -> None:
    with pytest.raises(ValueError, match="Sensitive pattern"):
        PrivacySanitizer.assert_safe_record({"unsafe": "13800138000"})
    with pytest.raises(ValueError, match="Sensitive pattern"):
        PrivacySanitizer.assert_safe_record({"unsafe": "Authorization: Bearer synthetic"})


def test_local_salt_is_created_owner_only(tmp_path: Path) -> None:
    salt_file = tmp_path / "secrets" / "hmac_salt"
    first = load_or_create_salt(salt_file)
    second = load_or_create_salt(salt_file)

    assert first == second
    assert len(first) >= 32
    assert stat.S_IMODE(salt_file.stat().st_mode) == 0o600


def test_privacy_safe_model_forbids_raw_pii_columns() -> None:
    with pytest.raises(ValueError, match="receiver_phone"):
        SanitizedOrderRecord.model_validate(
            {
                "order_anon_id": "Order_synthetic",
                "suborder_anon_id": "Suborder_synthetic",
                "ordered_at": None,
                "product_id": "Product_synthetic",
                "product_name_masked": "ProductName_synthetic",
                "sku_id": "SKU_synthetic",
                "sku_name_masked": "SKUName_synthetic",
                "creator_id": "",
                "unit_price_fen": 100,
                "quantity": 1,
                "merchant_income_fen": 90,
                "aftersale_status": None,
                "order_status": "paid",
                "has_product_tags": False,
                "source_record_id": "OrderRecord_synthetic",
                "receiver_phone": "synthetic-value",
            }
        )
