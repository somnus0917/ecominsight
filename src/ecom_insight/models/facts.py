from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class PrivacySafeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SanitizedOrderRecord(PrivacySafeModel):
    order_anon_id: str
    suborder_anon_id: str
    ordered_at: datetime | None
    product_id: str
    product_name_masked: str
    sku_id: str
    sku_name_masked: str
    creator_id: str
    unit_price_fen: int | None
    quantity: int | None
    merchant_income_fen: int | None
    aftersale_status: str | None
    order_status: str | None
    has_product_tags: bool
    source_record_id: str

    @field_validator("order_anon_id")
    @classmethod
    def order_id_is_anonymous(cls, value: str) -> str:
        if not value.startswith("Order_"):
            raise ValueError("order_anon_id must be an anonymized alias")
        return value


class SettlementRecord(PrivacySafeModel):
    settlement_line_id: str
    settled_at: datetime | None
    ordered_at: datetime | None
    order_anon_id: str
    suborder_anon_id: str
    settlement_account_id: str
    settlement_type: str | None
    has_pre_settlement_refund: str | None
    product_id: str
    product_name_masked: str
    quantity: int | None
    creator_id: str
    business_type: str | None
    order_type: str | None
    is_commission_waived: str | None
    merchant_entity_id: str
    app_channel: str | None
    source_record_id: str
    settlement_amount_fen: int | None
    order_total_fen: int | None
    product_total_fen: int | None
    shipping_fee_fen: int | None
    shop_coupon_fen: int | None
    government_subsidy_merchant_advance_fen: int | None
    pre_settlement_refund_fen: int | None
    platform_subsidy_fen: int | None
    other_platform_subsidy_fen: int | None
    government_subsidy_platform_advance_fen: int | None
    creator_subsidy_fen: int | None
    platform_payment_subsidy_fen: int | None
    monthly_payment_marketing_subsidy_fen: int | None
    bank_subsidy_fen: int | None
    trade_in_deduction_fen: int | None
    platform_shipping_subsidy_fen: int | None
    user_paid_fen: int | None
    income_total_fen: int | None
    platform_service_fee_fen: int | None
    creator_commission_fen: int | None
    service_provider_commission_fen: int | None
    channel_share_fen: int | None
    merchant_acquisition_service_fee_fen: int | None
    offsite_promotion_fee_fen: int | None
    other_share_fen: int | None
    expense_total_fen: int | None
    commission_waived_fen: int | None
