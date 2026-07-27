# EcomInsight

Multi-platform E-commerce Analytics, Anomaly Detection and Evidence-based Attribution System.

EcomInsight is a portfolio-grade analytics project built from real multi-source e-commerce
operations data. The system treats the language model as a report writer over verified evidence,
not as a calculator or a source of causal claims.

## Current status

- Phase 0 complete: read-only data audit, data dictionary and architecture.
- Phase 1 complete: Python 3.12/uv project, configuration, logging and quality tooling.
- Phase 2 complete: privacy-first adapters, Parquet staging and DuckDB warehouse.
- Anomaly detection, attribution, RAG, API and frontend remain later phases.

## Verified local data

- 165 shop-day operation rows: 105 Douyin and 60 external-platform rows.
- 23 channel shop-days, 186 product-days and 362 search/source rows.
- 11 independent inventory snapshots.
- 612 authoritative order rows containing direct personal information.
- 6198 settlement business lines after excluding four file-summary rows.

These counts come from the Phase 0 read-only audit and are not synthetic performance claims.

## Architecture

```text
read-only sources
→ allowlist/denylist discovery
→ streaming privacy sanitizer
→ unit-aware Parquet staging
→ data contracts
→ DuckDB curated facts and dimensions
→ metrics
→ anomaly detection
→ evidence rules
→ constrained LLM report
```

See:

- [Data audit](docs/data_audit.md)
- [Data dictionary](docs/data_dictionary.md)
- [Architecture](docs/architecture.md)
- [Warehouse implementation](docs/warehouse.md)
- [Privacy and security](docs/privacy_and_security.md)

## Privacy defaults

- Browser sessions, auth tables, config, logs and login screenshots are hard-excluded.
- Names, phones and addresses are removed before an order record can enter a DataFrame.
- Order, shop, product, SKU, creator, merchant and warehouse identifiers are stable HMAC aliases.
- The local HMAC salt is stored with mode `0600` outside version control.
- Real database, CSV, JSON, Parquet and DuckDB files are ignored.
- External APIs are disabled by default.

## Local setup

```bash
uv sync --all-groups
cp .env.example .env
```

Set `ECOM_SOURCE_ROOT` to the snapshot's `current` directory, then:

```bash
uv run ecom-audit-data
uv run ecom-build-warehouse
uv run pytest
```

The builder never modifies the source snapshot. Generated outputs are written under
`data/processed` and ignored by Git.

## Verified Phase 2 build

The warehouse was rebuilt twice against the audited snapshot with identical core row counts:

| Curated object | Rows |
|---|---:|
| `fact_shop_daily` | 165 |
| `fact_product_daily` | 186 |
| `fact_order_sanitized` | 612 |
| `fact_settlement` | 6198 |
| `fact_inventory_snapshot` | 12693 across 11 snapshots |
| `bridge_product_sku` | 7 candidate links |

The final quality report contains no failed checks. Its warning records 239 negative available
inventory observations across all historical snapshots; the latest snapshot contains the 28
already documented in Phase 0. Negative availability is retained rather than silently changed.

Curated money columns are `DECIMAL(18,2)` yuan. No raw receiver, phone, address, order-number,
credential or authentication columns exist in the generated warehouse.

## Known limitations

- Per-shop history is uneven: the four Douyin shops have 11, 39, 43 and 12 observations.
- Channel, product and search data cover only seven captured dates.
- Product IDs do not directly link platform product facts to WMS or settlement products.
- Current order and settlement extracts have no overlapping order identifiers.
- Activity calendars, price changes and ad-plan changes are not currently available, so
  correlations cannot be described as confirmed causes.
