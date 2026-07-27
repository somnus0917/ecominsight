# Phase 3 base analytics

## Run status

Phase 3 was executed against the sanitized Phase 2 DuckDB warehouse. No external API or model was
used. Actual currency totals remain in local Git-ignored artifacts and are not copied into this
document.

## Implemented marts

| Mart | Rows | Purpose |
|---|---:|---|
| `mart_shop_performance_daily` | 165 | Daily sales, funnel, refund, ad and settlement metrics |
| `mart_shop_summary` | 8 | Source-aware shop coverage and ratio-of-sums KPIs |
| `mart_product_summary` | 60 | Product contribution, rank, traffic and conversion |
| `mart_product_shop_coverage_daily` | 23 | Product-list coverage versus shop payment |
| `mart_channel_composition_daily` | 72 | Available channel-group mix |
| `mart_content_type_summary` | 20 | Content-type payment contribution |
| `mart_content_carrier_summary` | 28 | Carrier payment, traffic, refund and benchmark metrics |
| `mart_search_term_summary` | 108 | Shop/industry term rank and benchmark summaries |
| `mart_traffic_source_summary` | 23 | Search/source amount and exposure summaries |
| `mart_inventory_health_latest` | 1200 | Latest SKU-warehouse health |
| `mart_inventory_summary_latest` | 1 | Latest inventory portfolio summary |
| `mart_financial_daily` | 32 | Settlement-date income, fees, subsidy and settlement |
| `mart_financial_merchant_summary` | 3 | Masked merchant settlement summary |

## Evidence-backed findings

### Coverage is heterogeneous

The eight source-shop entities have 3, 4, 11, 12, 17, 36, 39 and 43 observation days. Analysis
retains the source scope and does not treat all shops as having a 56-day series.

### Product data is a partial contribution view

Product facts cover 23 shop-days. Six shop-days have a zero shop-payment denominator, so coverage
is undefined. Across defined days, captured-product coverage ranges from 0 to 1 and averages about
28.5%. Product facts should therefore support contribution and evidence retrieval, not a claim
that they fully reconcile shop sales.

### Channel groups are not exhaustive

The four available channel groups sum to 43.4%–93.2% of the recorded source metric, averaging about
79.0%. The remainder must stay “unclassified/other”; normalizing available groups to 100% would
overstate their contribution.

### Inventory rules are now reproducible

The latest snapshot contains 1200 SKU-warehouse rows:

- 28 negative-available rows;
- 449 rows with non-positive availability;
- 455 rows meeting the initial stockout-risk rule;
- 725 rows with positive stock and no observed seven-day sales;
- 6 positive-stock rows with no more than seven days of supply;
- 2 additional rows with seven to fourteen days of supply.

These are rule outputs, not confirmed loss-of-sales causes. Linking platform products to WMS SKUs
still requires confirmed bridge records.

### Finance remains settlement-date analysis

Financial marts cover 32 settlement dates and three masked merchant entities. Amount signs are
preserved. The analysis does not force reconciliation to payment-day shop metrics because current
order and settlement extracts do not share identifiers.

## Quality interpretation

`analysis_quality` distinguishes invalid values from partial coverage:

- channel shares below 100% are informational when they remain within 0–1;
- product coverage with a zero denominator is informational;
- ratios below 0 or materially above 1.0 are warnings.

This prevents expected truncation and unclassified traffic from being reported as pipeline
failures.

## Local outputs

The full masked results are generated locally:

```text
data/processed/artifacts/phase3_summary.json
data/processed/parquet/curated/mart_*.parquet
data/processed/ecom_insight.duckdb
```

These files remain Git-ignored because pseudonymized commercial aggregates are still not public
demo data.

