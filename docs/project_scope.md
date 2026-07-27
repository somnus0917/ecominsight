# Project scope

## Implemented

- Phase 0 read-only source audit and field mapping.
- Python 3.12 project managed by uv.
- Environment-based source configuration and structured redacted logging.
- Stable local HMAC aliases with a non-versioned owner-only salt.
- Independent SQLite, inventory, order, external-order and settlement adapters.
- PII-first streaming order sanitizer.
- Parquet staging with explicit integer-fen money fields.
- DuckDB curated facts with `DECIMAL(18,2)` yuan fields.
- Dimensions, product-SKU candidate bridge, quality report and build manifest.
- Centralized, validated registry for outcome, driver, guardrail and diagnostic metrics.
- Repeatable Phase 3 analysis pipeline covering shops, products, channels, search,
  inventory and settlement finance.
- Thirteen DuckDB analysis marts with Parquet exports and aggregate quality checks.
- Deterministic fully synthetic cross-domain demo data with controlled anomaly labels,
  reconciliation checks and privacy scanning.
- Unit tests for privacy, parsing, adapters, quality and money conversion.

## Deferred by design

- Phase 4 anomaly algorithms and comparison experiments.
- Phase 5 attribution rules and evidence graph.
- Phase 6 RAG and constrained LLM reporting.
- Phase 7 FastAPI, React, Docker and screenshots.

The deferred layers must consume curated facts. They may not reopen raw company files.
