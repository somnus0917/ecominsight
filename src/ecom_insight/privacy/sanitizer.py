from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path
from typing import Any

MAINLAND_MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
MAINLAND_ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
AUTHORIZATION_RE = re.compile(r"\bauthorization\s*:", re.IGNORECASE)
BEARER_RE = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
COOKIE_RE = re.compile(r"\b(?:cookie|set-cookie)\s*:", re.IGNORECASE)
TOKEN_ASSIGNMENT_RE = re.compile(
    r"\b(?:access[_-]?token|refresh[_-]?token|api[_-]?key)\s*[:=]\s*\S+",
    re.IGNORECASE,
)

RAW_PII_FIELDS = frozenset({"receiver_name", "receiver_phone", "receiver_address"})


def load_or_create_salt(path: Path, configured_salt: str | None = None) -> bytes:
    """Load a stable local HMAC salt or create one with owner-only permissions."""

    if configured_salt:
        encoded = configured_salt.encode("utf-8")
        if len(encoded) < 32:
            raise ValueError("Configured HMAC salt must contain at least 32 bytes")
        return encoded

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        value = path.read_bytes().strip()
        if len(value) < 32:
            raise ValueError(f"HMAC salt file is too short: {path}")
        return value

    value = secrets.token_hex(32).encode("ascii")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, value + b"\n")
    finally:
        os.close(descriptor)
    return value


class PrivacySanitizer:
    """Stable HMAC aliases and fail-closed sensitive-text checks."""

    def __init__(self, salt: bytes) -> None:
        if len(salt) < 32:
            raise ValueError("HMAC salt must contain at least 32 bytes")
        self._salt = salt

    def digest(self, namespace: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        payload = f"{namespace}\x1f{normalized}".encode()
        return hmac.new(self._salt, payload, hashlib.sha256).hexdigest()

    def alias(self, namespace: str, value: str, prefix: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        payload = f"{namespace}\x1f{normalized}".encode()
        digest = hmac.new(self._salt, payload, hashlib.sha256).digest()
        safe_digest = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
        return f"{prefix}_{safe_digest[:16]}"

    def shop_id(self, value: str) -> str:
        return self.alias("shop", value, "Shop")

    def product_id(self, value: str, source: str = "platform") -> str:
        return self.alias(f"{source}_product", value, "Product")

    def sku_id(self, value: str) -> str:
        return self.alias("sku", value, "SKU")

    def warehouse_id(self, value: str) -> str:
        return self.alias("warehouse", value, "Warehouse")

    def order_id(self, value: str) -> str:
        return self.alias("order", value, "Order")

    def suborder_id(self, value: str) -> str:
        return self.alias("suborder", value, "Suborder")

    def creator_id(self, value: str) -> str:
        return self.alias("creator", value, "Creator")

    def merchant_id(self, value: str) -> str:
        return self.alias("merchant", value, "Merchant")

    def masked_label(self, namespace: str, value: str, prefix: str) -> str:
        return self.alias(namespace, value, prefix)

    def sanitize_order_identifiers(self, row: dict[str, Any]) -> dict[str, Any]:
        """Delete direct PII and replace order identifiers before returning a row."""

        sanitized = dict(row)
        for field in RAW_PII_FIELDS:
            sanitized.pop(field, None)

        raw_order = str(sanitized.pop("order_no", "") or "")
        raw_suborder = str(sanitized.pop("item_order_id", "") or "")
        sanitized["order_anon_id"] = self.order_id(raw_order)
        sanitized["suborder_anon_id"] = self.suborder_id(raw_suborder)
        return sanitized

    @staticmethod
    def sensitive_matches(value: str) -> list[str]:
        matches: list[str] = []
        patterns = {
            "mainland_mobile": MAINLAND_MOBILE_RE,
            "mainland_id": MAINLAND_ID_RE,
            "authorization_header": AUTHORIZATION_RE,
            "bearer_token": BEARER_RE,
            "cookie_header": COOKIE_RE,
            "token_assignment": TOKEN_ASSIGNMENT_RE,
        }
        for name, pattern in patterns.items():
            if pattern.search(value):
                matches.append(name)
        return matches

    @classmethod
    def assert_safe_record(cls, record: dict[str, Any]) -> None:
        forbidden_columns = RAW_PII_FIELDS.intersection(record)
        if forbidden_columns:
            joined = ", ".join(sorted(forbidden_columns))
            raise ValueError(f"Forbidden PII columns survived sanitization: {joined}")
        for key, value in record.items():
            if isinstance(value, str):
                matches = cls.sensitive_matches(value)
                if matches:
                    raise ValueError(
                        f"Sensitive pattern(s) {matches} found in sanitized field {key}"
                    )
