from __future__ import annotations

import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from ecom_insight.demo.models import DemoConfig, DemoScenario
from ecom_insight.demo.profile import ReferenceProfile

Record = dict[str, Any]

CHANNELS = ("natural_search", "recommendation", "paid", "short_video", "live")
CHANNEL_WEIGHTS = (0.35, 0.25, 0.18, 0.14, 0.08)
PRODUCT_WEIGHTS = (0.34, 0.22, 0.16, 0.12, 0.09, 0.07)
SEARCH_WEIGHTS = (0.42, 0.27, 0.19, 0.12)


@dataclass(frozen=True, slots=True)
class GeneratedTables:
    shop_daily: list[Record]
    product_daily: list[Record]
    channel_daily: list[Record]
    search_term_daily: list[Record]
    inventory_daily: list[Record]
    financial_daily: list[Record]
    anomaly_labels: list[Record]

    def as_dict(self) -> dict[str, list[Record]]:
        return {
            "shop_daily": self.shop_daily,
            "product_daily": self.product_daily,
            "channel_daily": self.channel_daily,
            "search_term_daily": self.search_term_daily,
            "inventory_daily": self.inventory_daily,
            "financial_daily": self.financial_daily,
            "anomaly_labels": self.anomaly_labels,
        }


def _active_scenarios(
    config: DemoConfig,
) -> dict[tuple[str, int], list[DemoScenario]]:
    active: dict[tuple[str, int], list[DemoScenario]] = defaultdict(list)
    for scenario in config.scenarios:
        for day_index in range(scenario.start_day, scenario.start_day + scenario.duration_days):
            active[(scenario.shop_id, day_index)].append(scenario)
    return active


def _split_integer(total: int, weights: list[float]) -> list[int]:
    if not weights:
        return []
    denominator = sum(weights)
    allocated = [round(total * weight / denominator) for weight in weights[:-1]]
    allocated.append(total - sum(allocated))
    return allocated


def _split_amount(total: float, weights: list[float]) -> list[float]:
    if not weights:
        return []
    denominator = sum(weights)
    allocated = [round(total * weight / denominator, 2) for weight in weights[:-1]]
    allocated.append(round(total - sum(allocated), 2))
    return allocated


def _scenario_ids(scenarios: list[DemoScenario]) -> list[str]:
    return [scenario.scenario_id for scenario in scenarios]


def _scenario(scenarios: list[DemoScenario], scenario_type: str) -> DemoScenario | None:
    return next(
        (item for item in scenarios if item.scenario_type == scenario_type),
        None,
    )


def _shop_and_finance_rows(
    config: DemoConfig,
    profile: ReferenceProfile,
    rng: random.Random,
    active: dict[tuple[str, int], list[DemoScenario]],
) -> tuple[list[Record], list[Record]]:
    shop_rows: list[Record] = []
    finance_rows: list[Record] = []
    aov_bases = (178.0, 226.0, 315.0, 420.0)

    for shop_index, shop in enumerate(config.shops):
        for day_index in range(config.days):
            current_date = config.start_date + timedelta(days=day_index)
            scenarios = active.get((shop.shop_id, day_index), [])
            weekday_effect = 1.08 if current_date.weekday() >= 5 else 1.0
            smooth_seasonality = 1 + 0.07 * math.sin(day_index * math.tau / 7)
            trend = 1 + day_index * 0.0012
            noise = math.exp(rng.gauss(0, 0.035))

            exposure_users = (
                22_000 * shop.volume_factor * weekday_effect * smooth_seasonality * trend * noise
            )
            click_rate = profile.exposure_click_rate * (1 + rng.gauss(0, 0.025))
            conversion_rate = profile.click_conversion_rate * (1 + rng.gauss(0, 0.035))
            avg_order_value = aov_bases[shop_index % len(aov_bases)] * (
                1 + 0.025 * math.sin(day_index * math.tau / 30)
            )
            refund_rate = profile.refund_rate * (1 + rng.gauss(0, 0.05))

            traffic = _scenario(scenarios, "traffic_drop")
            ctr_drop = _scenario(scenarios, "click_rate_drop")
            conversion_drop = _scenario(scenarios, "conversion_drop")
            aov_drop = _scenario(scenarios, "aov_drop")
            refund_spike = _scenario(scenarios, "refund_spike")
            ad_waste = _scenario(scenarios, "ad_waste")
            stockout = _scenario(scenarios, "stockout")

            if traffic:
                exposure_users *= 1 - traffic.magnitude
            if ctr_drop:
                click_rate *= 1 - ctr_drop.magnitude
            if conversion_drop:
                conversion_rate *= 1 - conversion_drop.magnitude
            if aov_drop:
                avg_order_value *= 1 - aov_drop.magnitude
            if refund_spike:
                refund_rate *= 1 + refund_spike.magnitude
            if ad_waste:
                exposure_users *= 1.04
                conversion_rate *= 0.88
            if stockout:
                conversion_rate *= 0.52

            exposure_users_int = max(1, round(exposure_users))
            click_users = max(1, round(exposure_users_int * click_rate))
            paid_users = max(1, round(click_users * conversion_rate))
            paid_orders = max(paid_users, round(paid_users * 1.025))
            paid_items = max(paid_orders, round(paid_orders * 1.16))
            paid_amount = round(paid_users * avg_order_value, 2)
            avg_order_value = round(paid_amount / paid_users, 2)
            avg_item_price = round(paid_amount / paid_items, 2)
            exposure_count = round(exposure_users_int * 2.35)
            click_count = round(click_users * 1.22)
            click_rate = click_users / exposure_users_int
            conversion_rate = paid_users / click_users
            exposure_conversion_rate = paid_users / exposure_users_int
            refund_rate = min(max(refund_rate, 0.001), 0.55)
            refund_amount = round(paid_amount * refund_rate, 2)
            ad_spend = round(paid_amount * profile.ad_spend_ratio, 2)
            if ad_waste:
                ad_spend = round(ad_spend * (1 + ad_waste.magnitude), 2)
            roas = round(paid_amount / ad_spend, 4) if ad_spend else None

            platform_subsidy = round(paid_amount * 0.015, 2)
            creator_subsidy = round(paid_amount * 0.005, 2)
            platform_commission_rate = 0.04
            commission_spike = _scenario(scenarios, "commission_spike")
            if commission_spike:
                platform_commission_rate *= 1 + commission_spike.magnitude
            platform_commission = round(paid_amount * platform_commission_rate, 2)
            creator_commission = round(paid_amount * 0.03, 2)
            platform_service_fee = round(paid_amount * 0.012, 2)
            other_expense = round(paid_amount * 0.006, 2)
            settlement_adjustment = 0.0
            settlement_drop = _scenario(scenarios, "settlement_drop")
            if settlement_drop:
                settlement_adjustment = round(-paid_amount * settlement_drop.magnitude, 2)
            expense_amount = round(
                platform_commission
                + creator_commission
                + platform_service_fee
                + other_expense
                + refund_amount,
                2,
            )
            settlement_amount = round(
                paid_amount
                + platform_subsidy
                + creator_subsidy
                - expense_amount
                + settlement_adjustment,
                2,
            )
            scenario_ids = _scenario_ids(scenarios)

            shop_rows.append(
                {
                    "synthetic": True,
                    "dataset_version": config.dataset_version,
                    "date": current_date.isoformat(),
                    "platform": shop.platform,
                    "shop_id": shop.shop_id,
                    "shop_name_masked": shop.shop_id,
                    "scenario_ids": scenario_ids,
                    "gmv": round(paid_amount * 1.018, 2),
                    "paid_amount": paid_amount,
                    "net_paid_amount": round(paid_amount - refund_amount, 2),
                    "paid_orders": paid_orders,
                    "paid_items": paid_items,
                    "paid_users": paid_users,
                    "avg_order_value": avg_order_value,
                    "avg_item_price": avg_item_price,
                    "exposure_users": exposure_users_int,
                    "exposure_count": exposure_count,
                    "click_users": click_users,
                    "click_count": click_count,
                    "exposure_click_rate": round(click_rate, 8),
                    "click_conversion_rate": round(conversion_rate, 8),
                    "exposure_conversion_rate": round(exposure_conversion_rate, 8),
                    "gpm": round(paid_amount / exposure_users_int * 1000, 2),
                    "refund_amount": refund_amount,
                    "refund_rate": round(refund_rate, 8),
                    "ad_spend": ad_spend,
                    "roas": roas,
                    "platform_subsidy": platform_subsidy,
                    "creator_subsidy": creator_subsidy,
                    "platform_commission": platform_commission,
                    "creator_commission": creator_commission,
                    "expense_amount": expense_amount,
                    "settlement_amount": settlement_amount,
                    "merchant_experience_score": round(
                        min(
                            5.0,
                            max(
                                1.0,
                                profile.merchant_experience_score
                                + rng.gauss(0, 0.015)
                                - max(0.0, refund_rate - profile.refund_rate) * 0.3,
                            ),
                        ),
                        3,
                    ),
                }
            )
            finance_rows.append(
                {
                    "synthetic": True,
                    "dataset_version": config.dataset_version,
                    "date": current_date.isoformat(),
                    "shop_id": shop.shop_id,
                    "merchant_entity_id": f"Merchant_{shop.shop_id[-1]}",
                    "scenario_ids": scenario_ids,
                    "user_paid": paid_amount,
                    "income_total": round(paid_amount + platform_subsidy + creator_subsidy, 2),
                    "platform_subsidy": platform_subsidy,
                    "creator_subsidy": creator_subsidy,
                    "platform_commission": platform_commission,
                    "creator_commission": creator_commission,
                    "platform_service_fee": platform_service_fee,
                    "other_expense": other_expense,
                    "refund": refund_amount,
                    "settlement_adjustment": settlement_adjustment,
                    "expense_total": expense_amount,
                    "settlement_amount": settlement_amount,
                    "platform_commission_rate": round(platform_commission_rate, 8),
                    "settlement_ratio": round(settlement_amount / paid_amount, 8),
                }
            )
    return shop_rows, finance_rows


def _product_rows(
    config: DemoConfig,
    rng: random.Random,
    active: dict[tuple[str, int], list[DemoScenario]],
    shop_rows: list[Record],
) -> list[Record]:
    rows: list[Record] = []
    previous: dict[str, tuple[float, int]] = {}
    shop_lookup = {(row["shop_id"], row["date"]): row for row in shop_rows}

    for shop in config.shops:
        for day_index in range(config.days):
            current_date = config.start_date + timedelta(days=day_index)
            day_text = current_date.isoformat()
            shop_row = shop_lookup[(shop.shop_id, day_text)]
            scenarios = active.get((shop.shop_id, day_index), [])
            active_products = [
                index
                for index in range(config.products_per_shop)
                if index < config.products_per_shop - 1 or day_index >= 55
            ]
            weights = [
                PRODUCT_WEIGHTS[index] * math.exp(rng.gauss(0, 0.025)) for index in active_products
            ]
            stockout = _scenario(scenarios, "stockout")
            if stockout and stockout.target_product_index in active_products:
                target_position = active_products.index(stockout.target_product_index)
                weights[target_position] *= 0.12

            paid_amounts = _split_amount(float(shop_row["paid_amount"]), weights)
            exposures = _split_integer(int(shop_row["exposure_users"]), weights)
            paid_users = _split_integer(int(shop_row["paid_users"]), weights)
            paid_orders = _split_integer(int(shop_row["paid_orders"]), weights)

            for position, product_index in enumerate(active_products):
                product_id = f"Product_{shop.shop_id[-1]}_{product_index + 1:02d}"
                exposure = max(exposures[position], paid_users[position])
                product_paid_users = paid_users[position]
                product_click_rate = float(shop_row["exposure_click_rate"]) * (
                    0.90 + product_index * 0.035
                )
                click_users = max(
                    product_paid_users,
                    round(exposure * product_click_rate),
                )
                product_conversion = product_paid_users / click_users if click_users else 0.0
                paid_amount = paid_amounts[position]
                price = (
                    round(paid_amount / product_paid_users, 2)
                    if product_paid_users
                    else round(120 + product_index * 35, 2)
                )
                previous_amount, previous_exposure = previous.get(
                    product_id, (paid_amount, exposure)
                )
                paid_change = (
                    (paid_amount - previous_amount) / previous_amount if previous_amount else None
                )
                exposure_change = (
                    (exposure - previous_exposure) / previous_exposure
                    if previous_exposure
                    else None
                )
                first_listed_at = (
                    config.start_date + timedelta(days=55)
                    if product_index == config.products_per_shop - 1
                    else config.start_date - timedelta(days=90 + product_index * 10)
                )
                rows.append(
                    {
                        "synthetic": True,
                        "dataset_version": config.dataset_version,
                        "date": day_text,
                        "platform": shop.platform,
                        "shop_id": shop.shop_id,
                        "product_id": product_id,
                        "product_name_masked": f"Synthetic_{product_id}",
                        "scenario_ids": _scenario_ids(scenarios),
                        "price": price,
                        "paid_amount": paid_amount,
                        "paid_orders": paid_orders[position],
                        "paid_users": product_paid_users,
                        "exposure_users": exposure,
                        "click_users": click_users,
                        "click_rate": round(click_users / exposure, 8) if exposure else None,
                        "click_conversion_rate": round(product_conversion, 8)
                        if click_users
                        else None,
                        "paid_amount_change_rate": round(paid_change, 8)
                        if paid_change is not None
                        else None,
                        "exposure_change_rate": round(exposure_change, 8)
                        if exposure_change is not None
                        else None,
                        "first_listed_at": first_listed_at.isoformat(),
                    }
                )
                previous[product_id] = (paid_amount, exposure)
    return rows


def _channel_rows(
    config: DemoConfig,
    active: dict[tuple[str, int], list[DemoScenario]],
    shop_rows: list[Record],
) -> list[Record]:
    rows: list[Record] = []
    for shop_row in shop_rows:
        shop_id = str(shop_row["shop_id"])
        day_index = (date.fromisoformat(str(shop_row["date"])) - config.start_date).days
        scenarios = active.get((shop_id, day_index), [])
        weights = list(CHANNEL_WEIGHTS)
        if _scenario(scenarios, "traffic_drop"):
            weights[0] *= 0.45
        if _scenario(scenarios, "ad_waste"):
            weights[2] *= 1.65
        exposures = _split_integer(int(shop_row["exposure_users"]), weights)
        payment_weights = [
            exposure * efficiency
            for exposure, efficiency in zip(exposures, (1.05, 1.08, 0.92, 0.88, 1.12), strict=True)
        ]
        amounts = _split_amount(float(shop_row["paid_amount"]), payment_weights)
        for channel, exposure, amount in zip(CHANNELS, exposures, amounts, strict=True):
            rows.append(
                {
                    "synthetic": True,
                    "dataset_version": config.dataset_version,
                    "date": shop_row["date"],
                    "shop_id": shop_id,
                    "channel_id": f"Channel_{channel}",
                    "channel_group": channel,
                    "scenario_ids": _scenario_ids(scenarios),
                    "exposure_users": exposure,
                    "traffic_share": round(exposure / int(shop_row["exposure_users"]), 8),
                    "paid_amount": amount,
                    "paid_amount_share": round(amount / float(shop_row["paid_amount"]), 8),
                }
            )
    return rows


def _search_rows(
    config: DemoConfig,
    active: dict[tuple[str, int], list[DemoScenario]],
    channel_rows: list[Record],
) -> list[Record]:
    rows: list[Record] = []
    natural_rows = [row for row in channel_rows if row["channel_group"] == "natural_search"]
    for natural in natural_rows:
        shop_id = str(natural["shop_id"])
        current_date = date.fromisoformat(str(natural["date"]))
        day_index = (current_date - config.start_date).days
        scenarios = active.get((shop_id, day_index), [])
        exposures = _split_integer(
            int(natural["exposure_users"]),
            list(SEARCH_WEIGHTS[: config.search_terms_per_shop]),
        )
        amounts = _split_amount(
            float(natural["paid_amount"]),
            list(SEARCH_WEIGHTS[: config.search_terms_per_shop]),
        )
        traffic_drop = _scenario(scenarios, "traffic_drop")
        for term_index, (exposure, amount) in enumerate(zip(exposures, amounts, strict=True)):
            rank = 3 + term_index * 6 + (day_index % 5)
            if traffic_drop:
                rank += 12 + term_index * 2
            rows.append(
                {
                    "synthetic": True,
                    "dataset_version": config.dataset_version,
                    "date": natural["date"],
                    "shop_id": shop_id,
                    "term_kind": "shop_search",
                    "term_id": f"SearchTerm_{shop_id[-1]}_{term_index + 1:02d}",
                    "term_masked": f"Synthetic_SearchTerm_{term_index + 1:02d}",
                    "scenario_ids": _scenario_ids(scenarios),
                    "rank": rank,
                    "exposure_users": exposure,
                    "paid_amount": amount,
                    "benchmark_rank_lower": max(1, rank - 4),
                    "benchmark_rank_upper": rank + 5,
                }
            )
    return rows


def _inventory_rows(
    config: DemoConfig,
    active: dict[tuple[str, int], list[DemoScenario]],
    product_rows: list[Record],
) -> list[Record]:
    rows: list[Record] = []
    histories: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=7))
    for product in product_rows:
        shop_id = str(product["shop_id"])
        product_id = str(product["product_id"])
        current_date = date.fromisoformat(str(product["date"]))
        day_index = (current_date - config.start_date).days
        scenarios = active.get((shop_id, day_index), [])
        daily_sales = int(product["paid_orders"])
        histories[product_id].append(daily_sales)
        sales_7d = sum(histories[product_id])
        available_qty = max(6, math.ceil(sales_7d * 2.5))
        product_index = int(product_id[-2:]) - 1
        stockout = _scenario(scenarios, "stockout")
        overstock = _scenario(scenarios, "overstock")
        if stockout and stockout.target_product_index == product_index:
            available_qty = 0
        if overstock and overstock.target_product_index == product_index:
            available_qty = math.ceil(available_qty * (1 + overstock.magnitude))
        locked_qty = round(available_qty * 0.03)
        stock_qty = available_qty + locked_qty
        days_of_supply = (
            round(available_qty / (sales_7d / min(7, len(histories[product_id]))), 2)
            if sales_7d
            else None
        )
        rows.append(
            {
                "synthetic": True,
                "dataset_version": config.dataset_version,
                "snapshot_date": product["date"],
                "shop_id": shop_id,
                "warehouse_id": f"Warehouse_{shop_id[-1]}",
                "product_id": product_id,
                "sku_id": f"SKU_{product_id.removeprefix('Product_')}_01",
                "scenario_ids": _scenario_ids(scenarios),
                "stock_qty": stock_qty,
                "available_qty": available_qty,
                "locked_qty": locked_qty,
                "sales_7d": sales_7d,
                "inbound_30d": round(max(0, sales_7d * 2.8)),
                "days_of_supply": days_of_supply,
                "stockout_risk": available_qty <= max(2, sales_7d / 7 * 3),
                "overstock_flag": bool(days_of_supply is not None and days_of_supply >= 21),
            }
        )
    return rows


def _anomaly_labels(config: DemoConfig) -> list[Record]:
    labels: list[Record] = []
    for scenario in config.scenarios:
        start_date = config.start_date + timedelta(days=scenario.start_day)
        end_date = start_date + timedelta(days=scenario.duration_days - 1)
        labels.append(
            {
                "synthetic": True,
                "dataset_version": config.dataset_version,
                "label_source": "controlled_synthetic_injection",
                "scenario_id": scenario.scenario_id,
                "scenario_type": scenario.scenario_type,
                "entity_type": "shop",
                "entity_id": scenario.shop_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "target_metric": scenario.target_metric,
                "expected_direction": scenario.expected_direction,
                "expected_evidence": scenario.expected_evidence,
                "target_product_id": (
                    f"Product_{scenario.shop_id[-1]}_{scenario.target_product_index + 1:02d}"
                    if scenario.target_product_index is not None
                    else None
                ),
                "ground_truth_status": "synthetic_ground_truth",
            }
        )
    return labels


def generate_domain_tables(config: DemoConfig, profile: ReferenceProfile) -> GeneratedTables:
    rng = random.Random(config.seed)
    active = _active_scenarios(config)
    shop_rows, finance_rows = _shop_and_finance_rows(config, profile, rng, active)
    product_rows = _product_rows(config, rng, active, shop_rows)
    channel_rows = _channel_rows(config, active, shop_rows)
    search_rows = _search_rows(config, active, channel_rows)
    inventory_rows = _inventory_rows(config, active, product_rows)
    return GeneratedTables(
        shop_daily=shop_rows,
        product_daily=product_rows,
        channel_daily=channel_rows,
        search_term_daily=search_rows,
        inventory_daily=inventory_rows,
        financial_daily=finance_rows,
        anomaly_labels=_anomaly_labels(config),
    )
