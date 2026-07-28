from __future__ import annotations

import json
from pathlib import Path

import pytest

from ecom_insight.privacy.audit_profile import (
    assert_public_profile_safe,
    build_public_audit_profile,
)

PRIVATE_PROFILE_FIXTURE: dict[str, object] = {
    "schema_version": "0.1.0",
    "audit_scope": {
        "requested_source": "/Users/somnus/Documents/luopan/downloads/snapshot/current",
        "excluded_without_content_read": [
            "session/**",
            "state/luopan.db:sessions",
            "state/luopan.db:users",
            "state/luopan.db:app_kv.value_json",
        ],
    },
    "sqlite": {
        "luopan.db": {
            "tables": [
                {
                    "name": "operation_records",
                    "rows": 165,
                    "columns": ["shop_id TEXT", "date TEXT"],
                },
                {
                    "name": "sessions",
                    "rows": 3,
                    "columns": ["token_hash TEXT", "username TEXT", "expires_at INTEGER"],
                    "classification": "authentication_data_hard_excluded",
                },
                {
                    "name": "users",
                    "rows": 2,
                    "columns": ["username TEXT", "password_hash TEXT", "role TEXT"],
                    "classification": "authentication_data_hard_excluded",
                },
            ],
        },
    },
    "datasets": {
        "orders": {
            "rows": 612,
            "raw_columns": [
                "order_no",
                "receiver_name",
                "receiver_phone",
                "receiver_address",
                "product_name",
            ],
            "pii_presence_counts": {
                "receiver_name_nonempty": 612,
                "receiver_phone_nonempty": 612,
            },
        },
        "shop_daily": {
            "rows": 165,
            "metric_json_keys": ["pay_amt", "pay_cnt"],
        },
    },
    "quality_findings": [
        {
            "id": "DQ-001",
            "severity": "critical",
            "finding": "Order exports contain receiver name, phone and detailed address.",
            "risk": "Direct personal information could leak.",
        },
    ],
}


SENSITIVE_KEYWORDS = [
    "password_hash",
    "token_hash",
    "sessions",
    "users",
    "Cookie",
    "Authorization",
    "receiver_name",
    "receiver_phone",
    "receiver_address",
]


def test_public_profile_strips_absolute_paths() -> None:
    public = build_public_audit_profile(PRIVATE_PROFILE_FIXTURE)
    serialized = json.dumps(public, ensure_ascii=False)
    assert "/Users/" not in serialized
    assert "/home/" not in serialized


@pytest.mark.parametrize("keyword", SENSITIVE_KEYWORDS)
def test_public_profile_strips_sensitive_keywords(keyword: str) -> None:
    public = build_public_audit_profile(PRIVATE_PROFILE_FIXTURE)
    serialized = json.dumps(public, ensure_ascii=False)
    assert keyword not in serialized, f"Sensitive keyword {keyword!r} survived sanitization"


def test_public_profile_replaces_auth_tables_with_summary() -> None:
    public = build_public_audit_profile(PRIVATE_PROFILE_FIXTURE)
    tables = public["sqlite"]["luopan.db"]["tables"]  # type: ignore[index]
    auth_summaries = [
        t for t in tables  # type: ignore[union-attr]
        if isinstance(t, dict) and t.get("category") == "authentication_data"
    ]
    assert len(auth_summaries) == 1
    assert auth_summaries[0]["table_count"] == 2
    assert auth_summaries[0]["content_read"] is False


def test_public_profile_preserves_non_auth_tables() -> None:
    public = build_public_audit_profile(PRIVATE_PROFILE_FIXTURE)
    tables = public["sqlite"]["luopan.db"]["tables"]  # type: ignore[index]
    operation = [
        t for t in tables  # type: ignore[union-attr]
        if isinstance(t, dict) and t.get("name") == "operation_records"
    ]
    assert len(operation) == 1


def test_public_profile_strips_pii_columns_from_datasets() -> None:
    public = build_public_audit_profile(PRIVATE_PROFILE_FIXTURE)
    orders = public["datasets"]["orders"]  # type: ignore[index]
    assert "raw_columns" not in orders
    assert "pii_presence_counts" not in orders
    assert orders["rows"] == 612


def test_public_profile_sanitizes_quality_finding_text() -> None:
    public = build_public_audit_profile(PRIVATE_PROFILE_FIXTURE)
    findings = public["quality_findings"]  # type: ignore[index]
    assert findings[0]["finding"] == "Order exports contain direct personal information."


def test_assert_public_profile_safe_passes_on_clean_profile() -> None:
    public = build_public_audit_profile(PRIVATE_PROFILE_FIXTURE)
    assert_public_profile_safe(public)


def test_assert_public_profile_safe_fails_on_sensitive_content() -> None:
    bad = {"table": {"name": "sessions", "columns": ["token_hash"]}}
    with pytest.raises(ValueError, match="sensitive keyword"):
        assert_public_profile_safe(bad)


def test_assert_public_profile_safe_fails_on_absolute_path() -> None:
    bad = {"path": "/Users/somnus/secrets"}
    with pytest.raises(ValueError, match="absolute path"):
        assert_public_profile_safe(bad)


def test_existing_public_artifact_is_safe() -> None:
    artifact = Path("artifacts/data_profile.json")
    if not artifact.exists():
        pytest.skip("Public data profile artifact not generated yet")
    profile = json.loads(artifact.read_text(encoding="utf-8"))
    assert_public_profile_safe(profile)
