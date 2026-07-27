from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from statistics import fmean

from ecom_insight.demo.domains import GeneratedTables, Record
from ecom_insight.demo.models import DemoConfig, DemoScenario, ScenarioVerification
from ecom_insight.privacy import PrivacySanitizer


def _assert_close(actual: float, expected: float, tolerance: float, message: str) -> None:
    if abs(actual - expected) > tolerance:
        raise ValueError(f"{message}: actual={actual}, expected={expected}, tolerance={tolerance}")


def _average(rows: Iterable[Record], metric: str) -> float:
    values = [float(row[metric]) for row in rows if row.get(metric) is not None]
    if not values:
        raise ValueError(f"No values available for scenario metric: {metric}")
    return fmean(values)


def _window(
    rows: list[Record],
    date_field: str,
    start_date: date,
    end_date: date,
    **filters: str,
) -> list[Record]:
    return [
        row
        for row in rows
        if start_date <= date.fromisoformat(str(row[date_field])) <= end_date
        and all(str(row.get(field)) == value for field, value in filters.items())
    ]


def _validate_privacy(tables: GeneratedTables) -> None:
    for table_name, rows in tables.as_dict().items():
        for row in rows:
            if row.get("synthetic") is not True:
                raise ValueError(f"{table_name} contains a record not marked synthetic")
            try:
                PrivacySanitizer.assert_safe_record(row)
            except ValueError as error:
                raise ValueError(f"Privacy validation failed in {table_name}") from error


def _validate_shop_math(rows: list[Record]) -> None:
    for row in rows:
        exposure = int(row["exposure_users"])
        clicks = int(row["click_users"])
        paid_users = int(row["paid_users"])
        if not 0 <= paid_users <= clicks <= exposure:
            raise ValueError("Synthetic funnel counts are not monotonic")
        _assert_close(
            float(row["exposure_click_rate"]),
            clicks / exposure,
            1e-7,
            "Exposure-to-click rate mismatch",
        )
        _assert_close(
            float(row["click_conversion_rate"]),
            paid_users / clicks,
            1e-7,
            "Click conversion rate mismatch",
        )
        _assert_close(
            float(row["paid_amount"]),
            paid_users * float(row["avg_order_value"]),
            max(0.02, paid_users * 0.011),
            "Paid amount decomposition mismatch",
        )
        _assert_close(
            float(row["net_paid_amount"]),
            float(row["paid_amount"]) - float(row["refund_amount"]),
            0.011,
            "Net paid amount mismatch",
        )


def _validate_cross_domain_totals(tables: GeneratedTables) -> None:
    shop_index = {(str(row["shop_id"]), str(row["date"])): row for row in tables.shop_daily}
    product_totals: dict[tuple[str, str], float] = defaultdict(float)
    channel_amounts: dict[tuple[str, str], float] = defaultdict(float)
    channel_exposures: dict[tuple[str, str], int] = defaultdict(int)
    natural_index: dict[tuple[str, str], Record] = {}
    search_amounts: dict[tuple[str, str], float] = defaultdict(float)
    search_exposures: dict[tuple[str, str], int] = defaultdict(int)

    for row in tables.product_daily:
        product_totals[(str(row["shop_id"]), str(row["date"]))] += float(row["paid_amount"])
    for row in tables.channel_daily:
        key = (str(row["shop_id"]), str(row["date"]))
        channel_amounts[key] += float(row["paid_amount"])
        channel_exposures[key] += int(row["exposure_users"])
        if row["channel_group"] == "natural_search":
            natural_index[key] = row
    for row in tables.search_term_daily:
        key = (str(row["shop_id"]), str(row["date"]))
        search_amounts[key] += float(row["paid_amount"])
        search_exposures[key] += int(row["exposure_users"])

    for key, shop_row in shop_index.items():
        paid_amount = float(shop_row["paid_amount"])
        _assert_close(
            product_totals[key],
            paid_amount,
            0.05,
            "Product-to-shop paid amount mismatch",
        )
        _assert_close(
            channel_amounts[key],
            paid_amount,
            0.05,
            "Channel-to-shop paid amount mismatch",
        )
        if channel_exposures[key] != int(shop_row["exposure_users"]):
            raise ValueError("Channel exposure does not reconcile to shop exposure")
        natural = natural_index[key]
        _assert_close(
            search_amounts[key],
            float(natural["paid_amount"]),
            0.05,
            "Search-to-natural-channel paid amount mismatch",
        )
        if search_exposures[key] != int(natural["exposure_users"]):
            raise ValueError("Search exposure does not reconcile to natural channel")

    finance_index = {(str(row["shop_id"]), str(row["date"])): row for row in tables.financial_daily}
    if finance_index.keys() != shop_index.keys():
        raise ValueError("Financial daily coverage differs from shop daily coverage")
    for key, finance in finance_index.items():
        _assert_close(
            float(finance["user_paid"]),
            float(shop_index[key]["paid_amount"]),
            0.01,
            "Finance-to-shop paid amount mismatch",
        )
        expected_settlement = (
            float(finance["income_total"])
            - float(finance["expense_total"])
            + float(finance["settlement_adjustment"])
        )
        _assert_close(
            float(finance["settlement_amount"]),
            expected_settlement,
            0.02,
            "Settlement identity mismatch",
        )


def _metric_source(
    tables: GeneratedTables, scenario: DemoScenario
) -> tuple[list[Record], str, dict[str, str]]:
    if scenario.scenario_type in {"stockout", "overstock"}:
        product_id = _scenario_product_id(scenario)
        return (
            tables.inventory_daily,
            "snapshot_date",
            {"shop_id": scenario.shop_id, "product_id": product_id},
        )
    if scenario.scenario_type in {"commission_spike", "settlement_drop"}:
        return tables.financial_daily, "date", {"shop_id": scenario.shop_id}
    return tables.shop_daily, "date", {"shop_id": scenario.shop_id}


def _change(baseline: float, current: float) -> float | None:
    return (current - baseline) / abs(baseline) if baseline else None


def _scenario_product_id(scenario: DemoScenario) -> str:
    if scenario.target_product_index is None:
        raise ValueError(f"Scenario requires a target product: {scenario.scenario_id}")
    return f"Product_{scenario.shop_id[-1]}_{scenario.target_product_index + 1:02d}"


def _supporting_metrics(
    config: DemoConfig,
    tables: GeneratedTables,
    scenario: DemoScenario,
    baseline_start: date,
    baseline_end: date,
    scenario_start: date,
    scenario_end: date,
) -> dict[str, float | int | str | bool | None]:
    result: dict[str, float | int | str | bool | None] = {
        "baseline_days": 14,
        "scenario_days": scenario.duration_days,
    }

    def change_for(
        rows: list[Record],
        metric: str,
        date_field: str = "date",
        **filters: str,
    ) -> float | None:
        baseline_rows = _window(
            rows,
            date_field,
            baseline_start,
            baseline_end,
            **filters,
        )
        scenario_rows = _window(
            rows,
            date_field,
            scenario_start,
            scenario_end,
            **filters,
        )
        return round(
            _change(_average(baseline_rows, metric), _average(scenario_rows, metric)) or 0.0,
            6,
        )

    shop_filter = {"shop_id": scenario.shop_id}
    if scenario.scenario_type == "traffic_drop":
        result["natural_search_exposure_change_rate"] = change_for(
            tables.channel_daily,
            "exposure_users",
            channel_group="natural_search",
            **shop_filter,
        )
        result["search_rank_change_rate"] = change_for(
            tables.search_term_daily,
            "rank",
            **shop_filter,
        )
    elif scenario.scenario_type == "ad_waste":
        result["roas_change_rate"] = change_for(tables.shop_daily, "roas", **shop_filter)
    elif scenario.scenario_type == "stockout":
        product_id = _scenario_product_id(scenario)
        result["core_product_paid_amount_change_rate"] = change_for(
            tables.product_daily,
            "paid_amount",
            product_id=product_id,
            **shop_filter,
        )
        result["shop_conversion_change_rate"] = change_for(
            tables.shop_daily,
            "click_conversion_rate",
            **shop_filter,
        )
    elif scenario.scenario_type == "commission_spike":
        result["settlement_ratio_change_rate"] = change_for(
            tables.financial_daily,
            "settlement_ratio",
            **shop_filter,
        )
    elif scenario.scenario_type == "settlement_drop":
        result["paid_amount_change_rate"] = change_for(
            tables.shop_daily,
            "paid_amount",
            **shop_filter,
        )
    return result


def _verify_scenarios(config: DemoConfig, tables: GeneratedTables) -> list[ScenarioVerification]:
    verifications: list[ScenarioVerification] = []
    for scenario in config.scenarios:
        rows, date_field, filters = _metric_source(tables, scenario)
        scenario_start = config.start_date + timedelta(days=scenario.start_day)
        scenario_end = scenario_start + timedelta(days=scenario.duration_days - 1)
        baseline_end = scenario_start - timedelta(days=1)
        baseline_start = scenario_start - timedelta(days=14)
        baseline_rows = _window(rows, date_field, baseline_start, baseline_end, **filters)
        scenario_rows = _window(rows, date_field, scenario_start, scenario_end, **filters)
        baseline = _average(baseline_rows, scenario.target_metric)
        current = _average(scenario_rows, scenario.target_metric)
        change_rate = _change(baseline, current)
        if change_rate is None:
            passed = False
        elif scenario.expected_direction == "decrease":
            passed = change_rate <= -0.10
        else:
            passed = change_rate >= 0.10
        verification = ScenarioVerification(
            scenario_id=scenario.scenario_id,
            target_metric=scenario.target_metric,
            baseline_value=round(baseline, 6),
            scenario_value=round(current, 6),
            change_rate=round(change_rate, 6) if change_rate is not None else None,
            expected_direction=scenario.expected_direction,
            passed=passed,
            supporting_metrics=_supporting_metrics(
                config,
                tables,
                scenario,
                baseline_start,
                baseline_end,
                scenario_start,
                scenario_end,
            ),
        )
        if not verification.passed:
            raise ValueError(
                f"Synthetic scenario is not inferable from its target metric: "
                f"{scenario.scenario_id}"
            )
        verifications.append(verification)
    return verifications


def validate_generated_data(
    config: DemoConfig, tables: GeneratedTables
) -> list[ScenarioVerification]:
    _validate_privacy(tables)
    _validate_shop_math(tables.shop_daily)
    _validate_cross_domain_totals(tables)
    return _verify_scenarios(config, tables)
