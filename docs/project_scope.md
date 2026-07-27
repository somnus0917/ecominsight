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
- Unit tests for privacy, parsing, adapters, quality and money conversion.

## Deferred by design

- Phase 3 metric analysis beyond the initial YAML registry.
- Phase 4 anomaly algorithms and comparison experiments.
- Phase 5 attribution rules and evidence graph.
- Phase 6 RAG and constrained LLM reporting.
- Phase 7 FastAPI, React, Docker and screenshots.

The deferred layers must consume curated facts. They may not reopen raw company files.

