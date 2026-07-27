from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from ecom_insight.ingestion.base import AdapterOutput, Record
from ecom_insight.models import SanitizedOrderRecord
from ecom_insight.privacy import PrivacySanitizer
from ecom_insight.utils.parsing import (
    embedded_yuan_to_fen,
    parse_datetime,
    parse_price_quantity,
)


class OrdersAdapter:
    """Stream authoritative order CSV files and remove PII before materialization."""

    def __init__(self, orders_root: Path, privacy: PrivacySanitizer) -> None:
        self.orders_root = orders_root.resolve()
        self.privacy = privacy

    def authoritative_files(self) -> list[Path]:
        files: list[Path] = []
        for child in sorted(self.orders_root.iterdir()):
            if not child.is_dir() or not _is_iso_date(child.name):
                continue
            files.extend(sorted(child.rglob("douyin_orders_*.csv")))
        return files

    def extract(self) -> AdapterOutput:
        files = self.authoritative_files()
        records: list[Record] = []
        for path in files:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row_number, raw_row in enumerate(csv.DictReader(handle), start=2):
                    records.append(self._sanitize_row(raw_row, path, row_number))
        return AdapterOutput(
            tables={"stg_order_sanitized": records},
            source_files=files,
        )

    def _sanitize_row(
        self, raw_row: dict[str, str | None], source_file: Path, row_number: int
    ) -> Record:
        sanitized = self.privacy.sanitize_order_identifiers(
            {key: value or "" for key, value in raw_row.items()}
        )
        raw_product_name = str(sanitized.pop("product_name", "") or "")
        raw_sku_name = str(sanitized.pop("sku_spec", "") or "")
        raw_sku_code = str(sanitized.pop("merchant_sku_code", "") or "")
        raw_author = str(sanitized.pop("author", "") or "")
        price_fen, quantity = parse_price_quantity(sanitized.pop("price_quantity", None))

        record: Record = {
            "order_anon_id": sanitized.pop("order_anon_id"),
            "suborder_anon_id": sanitized.pop("suborder_anon_id"),
            "ordered_at": parse_datetime(sanitized.pop("order_time", None)),
            "product_id": self.privacy.alias(
                "order_product_name", raw_product_name, "OrderProduct"
            ),
            "product_name_masked": self.privacy.masked_label(
                "order_product_name", raw_product_name, "ProductName"
            ),
            "sku_id": self.privacy.sku_id(raw_sku_code),
            "sku_name_masked": self.privacy.masked_label("order_sku_name", raw_sku_name, "SKUName"),
            "creator_id": self.privacy.creator_id(raw_author),
            "unit_price_fen": price_fen,
            "quantity": quantity,
            "merchant_income_fen": embedded_yuan_to_fen(sanitized.pop("merchant_income", None)),
            "aftersale_status": _clean_category(sanitized.pop("aftersale_status", None)),
            "order_status": _clean_category(sanitized.pop("order_status", None)),
            "has_product_tags": bool(str(sanitized.pop("product_tags", "")).strip()),
            "source_record_id": self.privacy.alias(
                "order_source_record",
                f"{source_file.name}|{row_number}",
                "OrderRecord",
            ),
        }
        self.privacy.assert_safe_record(record)
        return SanitizedOrderRecord.model_validate(record).model_dump()


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _clean_category(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
