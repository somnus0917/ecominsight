from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ecom_insight.ingestion.base import AdapterOutput, Record
from ecom_insight.models import SettlementRecord
from ecom_insight.privacy import PrivacySanitizer
from ecom_insight.utils.parsing import parse_datetime, yuan_to_fen

SETTLEMENT_AMOUNT_FIELDS = {
    "结算金额": "settlement_amount_fen",
    "订单总价": "order_total_fen",
    "商品总价": "product_total_fen",
    "运费": "shipping_fee_fen",
    "店铺券": "shop_coupon_fen",
    "政府补贴商家垫资": "government_subsidy_merchant_advance_fen",
    "结算前退款金额": "pre_settlement_refund_fen",
    "平台补贴": "platform_subsidy_fen",
    "其他平台补贴": "other_platform_subsidy_fen",
    "政府补贴平台垫资": "government_subsidy_platform_advance_fen",
    "达人补贴": "creator_subsidy_fen",
    "抖音支付补贴": "platform_payment_subsidy_fen",
    "抖音月付营销补贴": "monthly_payment_marketing_subsidy_fen",
    "银行补贴": "bank_subsidy_fen",
    "以旧换新抵扣": "trade_in_deduction_fen",
    "平台补贴运费": "platform_shipping_subsidy_fen",
    "用户实付": "user_paid_fen",
    "收入合计": "income_total_fen",
    "平台服务费": "platform_service_fee_fen",
    "达人佣金": "creator_commission_fen",
    "服务商佣金": "service_provider_commission_fen",
    "渠道分成": "channel_share_fen",
    "招商服务费": "merchant_acquisition_service_fee_fen",
    "站外推广费": "offsite_promotion_fee_fen",
    "其他分成": "other_share_fen",
    "支出合计": "expense_total_fen",
    "免佣金额": "commission_waived_fen",
}


class SettlementAdapter:
    def __init__(self, settlement_root: Path, privacy: PrivacySanitizer) -> None:
        self.settlement_root = settlement_root.resolve()
        self.privacy = privacy

    def extract(self) -> AdapterOutput:
        files = sorted(self.settlement_root.glob("upload_*.csv"))
        facts: list[Record] = []
        summary_rows = 0
        for path in files:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row_number, raw in enumerate(csv.DictReader(handle), start=2):
                    order_no = str(raw.get("订单号", "") or "").strip()
                    suborder_no = str(raw.get("子订单号", "") or "").strip()
                    if not order_no and not suborder_no:
                        summary_rows += 1
                        continue
                    facts.append(self._sanitize_row(raw, path, row_number))

        warnings = [f"settlement_summary_rows_excluded:{summary_rows}"]
        return AdapterOutput(
            tables={"stg_settlement": facts},
            source_files=files,
            warnings=warnings,
        )

    def _sanitize_row(
        self, raw: dict[str, str | None], source_file: Path, row_number: int
    ) -> Record:
        order_no = str(raw.get("订单号", "") or "")
        suborder_no = str(raw.get("子订单号", "") or "")
        raw_product_id = str(raw.get("商品ID", "") or "")
        raw_creator = str(raw.get("达人ID", "") or raw.get("达人名称", "") or "")
        raw_merchant = str(raw.get("商户主体名称", "") or "")
        raw_account = str(raw.get("结算账户", "") or "")

        fact: Record = {
            "settlement_line_id": self.privacy.alias(
                "settlement_line",
                f"{source_file.name}|{row_number}",
                "SettlementLine",
            ),
            "settled_at": parse_datetime(raw.get("结算时间")),
            "ordered_at": parse_datetime(raw.get("下单时间")),
            "order_anon_id": self.privacy.order_id(order_no),
            "suborder_anon_id": self.privacy.suborder_id(suborder_no),
            "settlement_account_id": self.privacy.alias(
                "settlement_account", raw_account, "SettlementAccount"
            ),
            "settlement_type": _clean_category(raw.get("结算单类型")),
            "has_pre_settlement_refund": _clean_category(raw.get("有结算前退款")),
            "product_id": self.privacy.product_id(raw_product_id, source="settlement"),
            "product_name_masked": self.privacy.masked_label(
                "settlement_product", raw_product_id, "ProductName"
            ),
            "quantity": _optional_int(raw.get("商品数量")),
            "creator_id": self.privacy.creator_id(raw_creator),
            "business_type": _clean_category(raw.get("业务类型")),
            "order_type": _clean_category(raw.get("订单类型")),
            "is_commission_waived": _clean_category(raw.get("是否免佣")),
            "merchant_entity_id": self.privacy.merchant_id(raw_merchant),
            "app_channel": _clean_category(raw.get("APP渠道")),
            "source_record_id": self.privacy.alias(
                "settlement_source_record",
                f"{source_file.name}|{row_number}",
                "SettlementRecord",
            ),
        }
        for source_field, target_field in SETTLEMENT_AMOUNT_FIELDS.items():
            fact[target_field] = yuan_to_fen(raw.get(source_field))

        self.privacy.assert_safe_record(fact)
        return SettlementRecord.model_validate(fact).model_dump()


def _optional_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(float(str(value)))


def _clean_category(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
