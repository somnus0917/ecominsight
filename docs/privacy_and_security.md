# Privacy and security

## Denied sources

Browser sessions, storage state, cookies, login images, configuration, logs, authentication tables
and user/password tables are outside the analytics boundary.

## Order handling

The order adapter discovers only direct ISO-date directories. `test_*` and browser-state paths are
not authoritative. Each CSV row is processed in this order:

1. remove receiver name, phone and address;
2. remove raw order and item-order identifiers;
3. generate stable HMAC aliases;
4. mask product, SKU and creator values;
5. validate against a Pydantic model that forbids extra fields;
6. scan all surviving strings for blocked PII/credential patterns;
7. only then append the record for DataFrame construction.

## Secrets

When `ECOM_HMAC_SALT` is not configured, the builder creates
`data/.secrets/hmac_salt` with filesystem mode `0600`. The value is never logged and the directory
is ignored by Git.

## Processed data

Processed Parquet and DuckDB files remain commercially sensitive even though direct identifiers
are replaced. They are local artifacts, excluded from Git, and are not public demo data.

## External services

External API access is disabled by default. Later LLM integrations may receive only aggregated,
sanitized `EvidenceBundle` objects after explicit configuration.

