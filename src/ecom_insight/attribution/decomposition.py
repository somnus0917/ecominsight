from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from ecom_insight.attribution.models import FactorContribution, MetricDecomposition

PAID_AMOUNT_FACTORS = (
    "exposure_users",
    "exposure_click_rate",
    "click_conversion_rate",
    "avg_order_value",
)
PAID_AMOUNT_FORMULA = (
    "paid_amount ~= exposure_users * exposure_click_rate * click_conversion_rate * avg_order_value"
)


def _change_rate(current: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return current / baseline - 1


def decompose_multiplicative_change(
    *,
    target_metric: str,
    formula: str,
    factor_metrics: Sequence[str],
    current: Mapping[str, float | None],
    baseline: Mapping[str, float | None],
) -> MetricDecomposition:
    required = (target_metric, *factor_metrics)
    missing = [
        metric for metric in required if current.get(metric) is None or baseline.get(metric) is None
    ]
    if missing:
        return MetricDecomposition(
            target_metric=target_metric,
            formula=formula,
            method="insufficient_data",
            baseline_value=baseline.get(target_metric),
            current_value=current.get(target_metric),
            target_change_rate=None,
            target_log_change=None,
            explained_log_change=None,
            residual=None,
            limitations=[f"缺少分解字段: {', '.join(missing)}"],
        )

    values = {
        metric: (float(baseline[metric]), float(current[metric]))  # type: ignore[arg-type]
        for metric in required
    }
    target_baseline, target_current = values[target_metric]
    all_positive = all(
        baseline_value > 0 and current_value > 0
        for baseline_value, current_value in values.values()
    )
    if all_positive:
        factor_logs = {
            metric: math.log(current_value / baseline_value)
            for metric, (baseline_value, current_value) in values.items()
            if metric != target_metric
        }
        target_log_change = math.log(target_current / target_baseline)
        explained = sum(factor_logs.values())
        magnitude = sum(abs(value) for value in factor_logs.values())
        factors = [
            FactorContribution(
                metric=metric,
                baseline_value=values[metric][0],
                current_value=values[metric][1],
                change_rate=_change_rate(values[metric][1], values[metric][0]),
                log_change=factor_logs[metric],
                contribution_share=(abs(factor_logs[metric]) / magnitude if magnitude > 0 else 0.0),
            )
            for metric in factor_metrics
        ]
        return MetricDecomposition(
            target_metric=target_metric,
            formula=formula,
            method="log_change",
            baseline_value=target_baseline,
            current_value=target_current,
            target_change_rate=_change_rate(target_current, target_baseline),
            target_log_change=target_log_change,
            explained_log_change=explained,
            residual=target_log_change - explained,
            factors=factors,
        )

    factor_rates = {
        metric: _change_rate(current_value, baseline_value)
        for metric, (baseline_value, current_value) in values.items()
        if metric != target_metric
    }
    target_rate = _change_rate(target_current, target_baseline)
    valid_rates = [value for value in factor_rates.values() if value is not None]
    explained_rate = sum(valid_rates)
    magnitude = sum(abs(value) for value in valid_rates)
    factors = [
        FactorContribution(
            metric=metric,
            baseline_value=values[metric][0],
            current_value=values[metric][1],
            change_rate=factor_rates[metric],
            log_change=None,
            contribution_share=(
                abs(rate) / magnitude
                if (rate := factor_rates[metric]) is not None and magnitude > 0
                else None
            ),
        )
        for metric in factor_metrics
    ]
    limitations = [
        "目标值或分解因子包含非正数, 不能使用对数分解; 已切换为一阶相对变化近似.",
        "相对变化近似包含交叉项误差, 残差不能解释为单一业务原因.",
    ]
    if target_rate is None:
        limitations.append("目标基线为零, 无法计算目标变化率.")
    return MetricDecomposition(
        target_metric=target_metric,
        formula=formula,
        method="relative_change",
        baseline_value=target_baseline,
        current_value=target_current,
        target_change_rate=target_rate,
        target_log_change=None,
        explained_log_change=explained_rate,
        residual=target_rate - explained_rate if target_rate is not None else None,
        factors=factors,
        limitations=limitations,
    )


def decompose_paid_amount(
    *,
    current: Mapping[str, float | None],
    baseline: Mapping[str, float | None],
) -> MetricDecomposition:
    return decompose_multiplicative_change(
        target_metric="paid_amount",
        formula=PAID_AMOUNT_FORMULA,
        factor_metrics=PAID_AMOUNT_FACTORS,
        current=current,
        baseline=baseline,
    )
