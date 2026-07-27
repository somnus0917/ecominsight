from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ecom_insight.ingestion.base import AdapterOutput, Record
from ecom_insight.privacy import PrivacySanitizer
from ecom_insight.utils.parsing import parse_date, parse_datetime


class InventoryAdapter:
    def __init__(self, inventory_root: Path, privacy: PrivacySanitizer) -> None:
        self.inventory_root = inventory_root.resolve()
        self.privacy = privacy

    def extract(self) -> AdapterOutput:
        history_files = sorted((self.inventory_root / "history").glob("*.json"))
        latest_file = self.inventory_root / "inventory_snapshot.json"
        source_files = list(history_files)

        by_snapshot_date: dict[str, tuple[Path, dict[str, Any]]] = {}
        for path in history_files:
            payload = _read_json_object(path)
            snapshot_key = _snapshot_date(payload, path)
            by_snapshot_date[snapshot_key] = (path, payload)

        if latest_file.is_file():
            payload = _read_json_object(latest_file)
            snapshot_key = _snapshot_date(payload, latest_file)
            if snapshot_key not in by_snapshot_date:
                by_snapshot_date[snapshot_key] = (latest_file, payload)
                source_files.append(latest_file)

        inventory_rows: list[Record] = []
        flow_rows: list[Record] = []
        for snapshot_date_text, (_path, payload) in sorted(by_snapshot_date.items()):
            parsed_snapshot_date = parse_date(snapshot_date_text)
            captured_at = parse_datetime(payload.get("captured_at"))
            for raw in _records(payload.get("inventory")):
                warehouse_raw = str(raw.get("warehouse_no", ""))
                goods_raw = str(raw.get("goods_no", ""))
                sku_raw = str(raw.get("spec_no", ""))
                brand_raw = str(raw.get("brand_no", ""))
                inventory_rows.append(
                    {
                        "snapshot_date": parsed_snapshot_date,
                        "captured_at": captured_at,
                        "warehouse_id": self.privacy.warehouse_id(warehouse_raw),
                        "warehouse_name_masked": self.privacy.masked_label(
                            "warehouse", warehouse_raw, "Warehouse"
                        ),
                        "brand_id": self.privacy.alias("brand", brand_raw, "Brand"),
                        "brand_name_masked": self.privacy.masked_label("brand", brand_raw, "Brand"),
                        "goods_id": self.privacy.product_id(goods_raw, source="wms"),
                        "goods_name_masked": self.privacy.masked_label(
                            "wms_goods", goods_raw, "Goods"
                        ),
                        "sku_id": self.privacy.sku_id(sku_raw),
                        "sku_name_masked": self.privacy.masked_label("sku", sku_raw, "SKUName"),
                        "stock_qty": _optional_float(raw.get("stock_num")),
                        "available_qty": _optional_float(raw.get("available_num")),
                        "locked_qty": _optional_float(raw.get("lock_num")),
                        "today_qty": _optional_float(raw.get("today_num")),
                        "last_movement_at": parse_datetime(raw.get("last_inout_time")),
                        "source_modified_at": parse_datetime(raw.get("modified")),
                        "spec_name_missing": not bool(str(raw.get("spec_name", "")).strip()),
                    }
                )

            flow_rows.extend(
                self._flow_rows(
                    parsed_snapshot_date,
                    _records(payload.get("sales_7d")),
                    flow_type="sale",
                )
            )
            flow_rows.extend(
                self._flow_rows(
                    parsed_snapshot_date,
                    _records(payload.get("inbound_30d")),
                    flow_type="inbound",
                )
            )

        warnings: list[str] = []
        dates = sorted(by_snapshot_date)
        if "2026-07-19" not in by_snapshot_date and dates:
            warnings.append("inventory_snapshot_missing_date:2026-07-19")

        return AdapterOutput(
            tables={
                "stg_inventory_snapshot": inventory_rows,
                "stg_inventory_flow_daily": flow_rows,
            },
            source_files=source_files,
            warnings=warnings,
        )

    def _flow_rows(
        self, snapshot_date: Any, rows: list[dict[str, Any]], flow_type: str
    ) -> list[Record]:
        result: list[Record] = []
        for raw in rows:
            result.append(
                {
                    "snapshot_date": snapshot_date,
                    "flow_date": parse_date(raw.get("date")),
                    "warehouse_id": self.privacy.warehouse_id(str(raw.get("warehouse_no", ""))),
                    "sku_id": self.privacy.sku_id(str(raw.get("spec_no", ""))),
                    "flow_type": flow_type,
                    "quantity": _optional_float(raw.get("quantity")),
                }
            )
        return result


def _read_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object in inventory source: {path.name}")
    return payload


def _snapshot_date(payload: dict[str, Any], path: Path) -> str:
    captured_at = str(payload.get("captured_at", ""))
    if len(captured_at) >= 10:
        return captured_at[:10]
    if path.parent.name == "history":
        return path.stem
    raise ValueError(f"Inventory snapshot has no usable date: {path.name}")


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
