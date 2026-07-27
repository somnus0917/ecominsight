# Warehouse implementation

## Build outputs

The Phase 2 builder writes local, Git-ignored artifacts:

```text
data/processed/
├── ecom_insight.duckdb
├── parquet/
│   ├── staging/
│   └── curated/
└── artifacts/
    ├── build_manifest.json
    └── quality_report.json
```

Staging money columns use integer fen names such as `paid_amount_fen`. Curated fact columns remove
the suffix and use `DECIMAL(18,2)` yuan.

## Curated facts

| Table | Grain | Verified rows |
|---|---|---:|
| `fact_shop_daily` | shop × day | 165 |
| `fact_content_daily` | shop × day × content type | 483 |
| `fact_channel_daily` | shop × day × source/group | 200 |
| `fact_content_carrier_daily` | shop × day × carrier | 161 |
| `fact_product_daily` | shop × day × platform product | 186 |
| `fact_search_term_daily` | shop × day × term kind × term | 230 |
| `fact_traffic_source_daily` | shop × day × traffic source | 132 |
| `fact_inventory_snapshot` | snapshot × warehouse × SKU | 12693 |
| `fact_inventory_flow_daily` | as-of snapshot × flow date × warehouse × SKU × type | 8979 |
| `fact_order_sanitized` | anonymous order/item row | 612 |
| `fact_settlement` | settlement line | 6198 |
| `fact_external_shop_daily` | external shop × day | 60 |

## Dimensions and links

The build creates `dim_date`, `dim_platform`, `dim_shop`, `dim_product`, `dim_sku`,
`dim_channel`, `dim_content_type` and `dim_warehouse`.

`bridge_product_sku` contains seven observed order-product/SKU links whose merchant SKU alias also
exists in WMS inventory. They remain `candidate` with confidence 0.70 until business semantics are
confirmed.

## Quality result

The audited build has 46 checks:

- no failed checks;
- one warning;
- the warning records 239 negative available-inventory observations across all 11 snapshots;
- the latest snapshot contributes 28, matching the Phase 0 audit.

The builder retains negative availability as evidence and does not silently coerce it to zero.

## Query examples

```sql
SELECT date, shop_id, paid_amount, exposure_users
FROM fact_shop_daily
ORDER BY date, shop_id;
```

```sql
SELECT snapshot_date, count(*) AS negative_available_rows
FROM fact_inventory_snapshot
WHERE available_qty < 0
GROUP BY snapshot_date
ORDER BY snapshot_date;
```

```sql
SELECT *
FROM bridge_product_sku
WHERE link_status = 'candidate';
```

Queries return only HMAC aliases and masked labels. The warehouse has no raw receiver name, phone,
address, order-number, password or token columns.

