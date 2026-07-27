from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb


@dataclass(frozen=True, slots=True)
class ReferenceProfile:
    exposure_click_rate: float
    click_conversion_rate: float
    refund_rate: float
    ad_spend_ratio: float
    merchant_experience_score: float
    reference_used: bool
    reference_fields: tuple[str, ...]

    @classmethod
    def defaults(cls) -> ReferenceProfile:
        return cls(
            exposure_click_rate=0.12,
            click_conversion_rate=0.055,
            refund_rate=0.06,
            ad_spend_ratio=0.08,
            merchant_experience_score=4.75,
            reference_used=False,
            reference_fields=(),
        )


def _bounded(value: float | None, default: float, lower: float, upper: float) -> float:
    if value is None or not lower <= value <= upper:
        return default
    return value


def load_reference_profile(database_path: Path | None) -> ReferenceProfile:
    """Read only non-identifying rate medians from the sanitized local warehouse."""

    defaults = ReferenceProfile.defaults()
    if database_path is None or not database_path.is_file():
        return defaults

    with duckdb.connect(str(database_path), read_only=True) as connection:
        values = connection.execute(
            """
            SELECT
                median(exposure_click_rate_users)
                    FILTER (WHERE exposure_click_rate_users BETWEEN 0.01 AND 0.80),
                median(click_conversion_rate_users)
                    FILTER (WHERE click_conversion_rate_users BETWEEN 0.005 AND 0.80),
                median(refund_rate_by_pay_time)
                    FILTER (WHERE refund_rate_by_pay_time BETWEEN 0 AND 0.80),
                median(ad_spend / NULLIF(paid_amount, 0))
                    FILTER (
                        WHERE ad_spend >= 0
                          AND paid_amount > 0
                          AND ad_spend / paid_amount BETWEEN 0 AND 0.80
                    ),
                median(merchant_experience_score)
                    FILTER (WHERE merchant_experience_score BETWEEN 1 AND 5)
            FROM fact_shop_daily
            """
        ).fetchone()

    if values is None:
        return defaults
    return ReferenceProfile(
        exposure_click_rate=_bounded(values[0], defaults.exposure_click_rate, 0.04, 0.35),
        click_conversion_rate=_bounded(values[1], defaults.click_conversion_rate, 0.015, 0.25),
        refund_rate=_bounded(values[2], defaults.refund_rate, 0.005, 0.30),
        ad_spend_ratio=_bounded(values[3], defaults.ad_spend_ratio, 0.01, 0.40),
        merchant_experience_score=_bounded(values[4], defaults.merchant_experience_score, 3.0, 5.0),
        reference_used=True,
        reference_fields=(
            "exposure_click_rate_users",
            "click_conversion_rate_users",
            "refund_rate_by_pay_time",
            "ad_spend_to_paid_amount_ratio",
            "merchant_experience_score",
        ),
    )
