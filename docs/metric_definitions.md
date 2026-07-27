# Metric framework

The executable source of truth is [`configs/metrics.yaml`](../configs/metrics.yaml). It is loaded
through a strict Pydantic registry and published to DuckDB as `metric_registry`.

## Operating-review framework

### Primary outcomes

- `paid_amount`: shop-day user payment amount.
- `settlement_amount`: settlement-line amount aggregated by settlement date.

They are intentionally separate. The current extracts cannot reliably join payment-day shop facts
to settlement lines.

### Drivers

The primary diagnostic chain is:

```text
paid amount
≈ exposure users
× exposure click rate
× click conversion rate
× average order value
```

Other drivers include orders, paid users, GPM, ROAS, product payment, traffic share, recent sales
and search rank.

### Guardrails

- refund rate by payment time;
- ad spend;
- settlement fees and creator commission;
- available inventory;
- days of supply;
- stockout risk.

Guardrails are not target values in Phase 3. Current history and business thresholds are
insufficient to claim stable targets.

## Aggregation rules

- money is summed only within a compatible grain and source scope;
- average order value, conversion and ROAS use ratios of sums;
- daily unique users are labelled as day-sums when aggregated across dates;
- rates and ranks are non-additive;
- inventory rolling flows use only the latest as-of snapshot;
- settlement amounts retain source signs;
- missing observations remain null unless the source explicitly supplies an observed zero.

## Registry validation

The registry rejects:

- duplicate metric codes;
- framework references to undefined metrics;
- primary KPIs not labelled as outcomes;
- driver/guardrail role mismatches;
- non-declarative formula strings;
- metrics without grain, unit, aggregation, null policy or minimum history.

The current registry contains 32 metrics:

| Role | Count |
|---|---:|
| Outcome | 2 |
| Driver | 12 |
| Guardrail | 8 |
| Diagnostic | 10 |

