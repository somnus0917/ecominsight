from __future__ import annotations

import csv
from pathlib import Path

from ecom_insight.ingestion.settlement import SETTLEMENT_AMOUNT_FIELDS, SettlementAdapter
from ecom_insight.privacy import PrivacySanitizer


def test_summary_row_is_excluded_and_amount_is_converted(tmp_path: Path) -> None:
    root = tmp_path / "settlement"
    root.mkdir()
    fields = [
        "结算时间",
        "订单号",
        "子订单号",
        "下单时间",
        "结算账户",
        "结算单类型",
        "有结算前退款",
        "商品ID",
        "商品名称",
        "商品数量",
        "达人ID",
        "达人名称",
        "业务类型",
        "订单类型",
        "是否免佣",
        "商户主体名称",
        "APP渠道",
        *SETTLEMENT_AMOUNT_FIELDS,
    ]
    path = root / "upload_synthetic.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"结算金额": "100.00"})
        row = dict.fromkeys(fields, "")
        row.update(
            {
                "结算时间": "2026-01-02 00:00:00",
                "订单号": "synthetic-order",
                "子订单号": "synthetic-suborder",
                "下单时间": "2026-01-01 00:00:00",
                "商品ID": "synthetic-product",
                "商品数量": "1",
                "商户主体名称": "synthetic-merchant",
                "结算金额": "-1.23",
            }
        )
        writer.writerow(row)

    output = SettlementAdapter(root, PrivacySanitizer(b"x" * 32)).extract()
    rows = output.tables["stg_settlement"]

    assert len(rows) == 1
    assert rows[0]["settlement_amount_fen"] == -123
    assert rows[0]["merchant_entity_id"].startswith("Merchant_")
    assert output.warnings == ["settlement_summary_rows_excluded:1"]
