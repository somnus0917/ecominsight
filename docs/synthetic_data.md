# Synthetic data and controlled anomaly design

## Purpose

The audited company snapshot is sufficient for warehouse construction and descriptive analysis,
but several series are too short or cannot be linked strongly enough for reliable anomaly and
attribution evaluation. The synthetic layer fills those evaluation gaps without changing or
relabeling any real record.

The public dataset is fully synthetic. It is not presented as additional company history and must
not be mixed into real business totals.

## What is referenced

When the local sanitized Phase 2 DuckDB exists, the generator reads only bounded medians for:

- exposure-to-click rate;
- click conversion rate;
- refund rate;
- ad-spend-to-paid-amount ratio;
- merchant experience score.

It does not copy real rows, amounts, dates, names or IDs. Synthetic amount levels, entities and
dates are independently generated. Without the local warehouse, safe e-commerce defaults are
used.

## Dataset

The committed `demo-v1` dataset contains 140 days from 2025-01-06 through 2025-05-25:

| Dataset | Grain | Rows |
|---|---|---:|
| `shop_daily.json` | date × shop | 560 |
| `product_daily.json` | date × shop × product | 3,140 |
| `channel_daily.json` | date × shop × channel | 2,800 |
| `search_term_daily.json` | date × shop × search term | 2,240 |
| `inventory_daily.json` | date × shop × product × SKU × warehouse | 3,140 |
| `financial_daily.json` | date × shop × merchant | 560 |
| `anomaly_labels.json` | controlled scenario | 10 |

All rates use decimal `0–1`; all amounts use CNY yuan. Every row contains `synthetic=true`,
`dataset_version` and `scenario_ids`.

## Business identities

Generation fails unless these relationships reconcile:

```text
paid_amount ≈ paid_users × avg_order_value
paid_users ≤ click_users ≤ exposure_users
Σ product paid_amount = shop paid_amount
Σ channel paid_amount = shop paid_amount
Σ search paid_amount = natural-search paid_amount
settlement_amount = income_total - expense_total + settlement_adjustment
```

Missing values are retained when a ratio is undefined. They are not silently replaced with zero.

## Controlled scenarios and observed effects

Effects below are calculated by the generator from the scenario window versus its preceding
14-day baseline. They are synthetic test results, not company performance claims.

| Scenario | Primary observed effect | Corroborating evidence |
|---|---:|---|
| Traffic decline | exposure users −42.9% | natural-search exposure −68.2%; search rank worsened |
| Click-rate decline | exposure-to-click rate −43.3% | click users and payment decline |
| Conversion decline | click conversion rate −48.0% | paid users and payment decline |
| Average-order-value decline | average order value −36.9% | item price and payment decline |
| Refund spike | refund rate +225.7% | refund amount rises; net payment declines |
| Overstock | days of supply +300.1% | available quantity rises without matching sales |
| Inefficient ad spend | ad spend +119.0% | ROAS −58.3% |
| Core-SKU stockout | available quantity −100.0% | core-product payment −91.7%; conversion −48.3% |
| Commission spike | commission rate +180.0% | settlement ratio −8.5% |
| Settlement drop | settlement ratio −32.3% | paid amount remains broadly stable |

The generated `scenario_verification.json` is the machine-readable evidence for these checks.
Generation stops if any expected direction is not observable.

## Evaluation policy

- Real-data detection results and synthetic-label results are reported separately.
- Synthetic labels may measure algorithm recall, precision, detection delay and attribution
  evidence coverage.
- They must not be used to claim real-world business lift or production accuracy.
- A model must not receive `scenario_ids` or anomaly labels as input features.
- The random seed and scenario configuration are versioned for reproducibility.

## Commands

```bash
uv run ecom-generate-demo-data
uv run pytest tests/unit/test_demo_generator.py
```

Configuration is in `configs/demo_scenarios.yaml`; generated artifacts are under
`data/demo/generated/`.
