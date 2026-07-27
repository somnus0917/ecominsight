# Data directories

- `raw/`: never committed; this project reads the configured source snapshot in place.
- `processed/`: local DuckDB and Parquet outputs; sensitive and ignored by Git.
- `artifacts/`: local manifests and quality reports; ignored by Git.
- `demo/`: reserved for explicitly synthetic, automatically scanned public demo data.

No real company data is copied into this repository.

