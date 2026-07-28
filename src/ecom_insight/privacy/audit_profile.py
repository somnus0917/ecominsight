"""Public-safe audit profile generation.

Splits a full (private) data audit profile into a public-safe version that
strips authentication table structures, raw PII column names, absolute paths
and business identifiers while preserving aggregate structural findings.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any

_ABSOLUTE_PATH_RE = re.compile(r"/(?:Users|home)/[^\s\"',)}\]]+")

_AUTH_TABLE_NAMES = frozenset({"sessions", "users", "app_kv"})

_SENSITIVE_COLUMN_NAMES = frozenset({
    "token_hash",
    "password_hash",
    "password_changed_at",
    "username",
})

_PII_FIELD_NAMES = frozenset({
    "receiver_name",
    "receiver_phone",
    "receiver_address",
    "order_no",
    "item_order_id",
    "merchant_sku_code",
})

_SENSITIVE_KEYWORDS = frozenset({
    "password_hash",
    "token_hash",
    "sessions",
    "users",
    "Cookie",
    "Authorization",
    "receiver_name",
    "receiver_phone",
    "receiver_address",
})


def _replace_absolute_paths(value: Any) -> Any:
    if isinstance(value, str):
        return _ABSOLUTE_PATH_RE.sub("<LOCAL_SNAPSHOT_ROOT>", value)
    if isinstance(value, Mapping):
        return {k: _replace_absolute_paths(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace_absolute_paths(item) for item in value]
    return value


def _is_auth_table(table_entry: Mapping[str, Any]) -> bool:
    name = str(table_entry.get("name", ""))
    classification = str(table_entry.get("classification", ""))
    return name in _AUTH_TABLE_NAMES or "authentication" in classification


def _sanitize_sqlite_tables(tables: list[Any]) -> list[Any]:
    sanitized: list[Any] = []
    auth_count = 0
    for table in tables:
        if isinstance(table, Mapping) and _is_auth_table(table):
            auth_count += 1
            continue
        sanitized.append(table)
    if auth_count:
        sanitized.append({
            "category": "authentication_data",
            "status": "hard_excluded",
            "table_count": auth_count,
            "content_read": False,
        })
    return sanitized


def _sanitize_sqlite_section(sqlite: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for db_name, db_profile in sqlite.items():
        if not isinstance(db_profile, Mapping):
            result[db_name] = db_profile
            continue
        tables = db_profile.get("tables", [])
        sanitized_tables = _sanitize_sqlite_tables(tables) if isinstance(tables, list) else tables
        sanitized_db = {k: v for k, v in db_profile.items() if k != "tables"}
        sanitized_db["tables"] = sanitized_tables
        result[db_name] = sanitized_db
    return result


def _sanitize_dataset(dataset: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in dataset.items():
        if key in {"raw_columns", "pii_presence_counts", "commercial_sensitive_presence_counts"}:
            continue
        if key == "payload_fields" and isinstance(value, list):
            filtered = [f for f in value if f not in _PII_FIELD_NAMES]
            result[key] = filtered
            continue
        result[key] = value
    return result


def _sanitize_datasets(datasets: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: _sanitize_dataset(dataset) if isinstance(dataset, Mapping) else dataset
        for name, dataset in datasets.items()
    }


def _sanitize_excluded_list(items: list[Any]) -> list[Any]:
    sanitized: list[Any] = []
    for item in items:
        if isinstance(item, str):
            if any(auth in item for auth in _AUTH_TABLE_NAMES):
                continue
            if any(pii in item for pii in _PII_FIELD_NAMES):
                continue
        sanitized.append(item)
    if len(sanitized) < len(items):
        sanitized.append("authentication_data:hard_excluded")
    return sanitized


def _sanitize_quality_findings(findings: list[Any]) -> list[Any]:
    result: list[Any] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            result.append(finding)
            continue
        sanitized = dict(finding)
        for field in ("finding", "risk", "required_control"):
            text = sanitized.get(field)
            if isinstance(text, str):
                text = text.replace("receiver name, phone and detailed address", "direct personal information")
                text = text.replace("name, phone and detailed address", "direct personal information")
                text = text.replace("receiver name", "direct personal information")
                text = text.replace("receiver phone", "direct personal information")
                text = text.replace("receiver address", "direct personal information")
                sanitized[field] = text
        result.append(sanitized)
    return result


def build_public_audit_profile(
    private_profile: dict[str, object],
) -> dict[str, object]:
    """Produce a public-safe audit profile from a private full-profile dict.

    Strips absolute paths, authentication table structures, raw PII column
    names and business identifiers while preserving aggregate structural
    findings and quality observations.
    """
    public = copy.deepcopy(private_profile)
    public = _replace_absolute_paths(public)

    assert isinstance(public, dict)

    audit_scope = public.get("audit_scope")
    if isinstance(audit_scope, dict):
        excluded = audit_scope.get("excluded_without_content_read")
        if isinstance(excluded, list):
            audit_scope["excluded_without_content_read"] = _sanitize_excluded_list(excluded)
        public["audit_scope"] = audit_scope

    sqlite = public.get("sqlite")
    if isinstance(sqlite, Mapping):
        public["sqlite"] = _sanitize_sqlite_section(sqlite)

    datasets = public.get("datasets")
    if isinstance(datasets, Mapping):
        public["datasets"] = _sanitize_datasets(datasets)

    findings = public.get("quality_findings")
    if isinstance(findings, list):
        public["quality_findings"] = _sanitize_quality_findings(findings)

    return public


def assert_public_profile_safe(profile: object) -> None:
    """Raise ValueError if a profile still contains sensitive content."""
    serialized = repr(profile)
    for keyword in _SENSITIVE_KEYWORDS:
        if keyword in serialized:
            raise ValueError(f"Public audit profile contains sensitive keyword: {keyword}")
    for match in _ABSOLUTE_PATH_RE.finditer(serialized):
        raise ValueError(f"Public audit profile contains absolute path: {match.group()}")
