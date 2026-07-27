from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ecom_insight.ingestion.base import AdapterOutput, Record
from ecom_insight.privacy import PrivacySanitizer
from ecom_insight.utils.parsing import fen_to_yuan_fen, parse_date


class ExternalOrdersAdapter:
    def __init__(self, source_file: Path, privacy: PrivacySanitizer) -> None:
        self.source_file = source_file.resolve()
        self.privacy = privacy

    def extract(self) -> AdapterOutput:
        with self.source_file.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            raise ValueError("External orders source must contain a records array")

        facts: list[Record] = []
        for raw in payload["records"]:
            if not isinstance(raw, dict):
                continue
            metrics = raw.get("metrics")
            if not isinstance(metrics, dict):
                metrics = {}
            raw_shop_id = str(raw.get("shop_id", ""))
            source_label = str(raw.get("source_label", ""))
            facts.append(
                {
                    "date": parse_date(raw.get("date")),
                    "platform_id": self.privacy.alias("platform", source_label, "Platform"),
                    "shop_id": self.privacy.shop_id(raw_shop_id),
                    "shop_name_masked": self.privacy.shop_id(raw_shop_id),
                    "gmv_fen": fen_to_yuan_fen(metrics.get("income_amt")),
                    "paid_amount_fen": fen_to_yuan_fen(metrics.get("pay_amt")),
                    "paid_orders": _optional_int(metrics.get("pay_cnt")),
                    "paid_items": _optional_int(metrics.get("pay_item_cnt")),
                    "source_key_id": self.privacy.alias(
                        "external_source", str(raw.get("source_key", "")), "ExternalSource"
                    ),
                    "source_record_id": self.privacy.alias(
                        "external_record",
                        f"{raw_shop_id}|{raw.get('date', '')}",
                        "ExternalRecord",
                    ),
                }
            )
        return AdapterOutput(
            tables={"stg_external_shop_daily": facts},
            source_files=[self.source_file],
        )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
