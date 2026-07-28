"""Public repository safety scanner.

Scans Git-tracked files for sensitive content that must not be published:
absolute paths, phone/ID numbers, credentials, private keys, real data files
and sensitive audit-profile fields.

Returns a non-zero exit code when any finding is detected. Output is limited
to file name, line number and rule type to avoid echoing sensitive values.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ABSOLUTE_PATH_RE = re.compile(r"/(?:Users|home)/[^\s\"',)}\]]+|[A-Z]:\\\\[^\s\"',)}\]]+")
WINDOWS_PATH_RE = re.compile(r"[A-Z]:\\[^\s\"',)}\]]+")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
COOKIE_RE = re.compile(r"\b(?:cookie|set-cookie)\s*:", re.IGNORECASE)
AUTHORIZATION_RE = re.compile(r"\bauthorization\s*:\s*\S+", re.IGNORECASE)
BEARER_RE = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
TOKEN_ASSIGNMENT_RE = re.compile(
    r"\b(?:access[_-]?token|refresh[_-]?token|api[_-]?key|secret[_-]?key)\s*[:=]\s*[^\s]",
    re.IGNORECASE,
)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")
ENV_SECRET_VALUE_RE = re.compile(
    r"^\s*(?:ECOM_|POSTGRES_|REDIS_|AWS_)"
    r"(?:[A-Z_]*(?:KEY|SECRET|TOKEN|PASSWORD|SALT|CREDENTIAL)[A-Z_]*)"
    r"\s*=\s*(?!<placeholder>)(?!your_)(?!\.$)(?!false|true|null|none)"
    r"(?!\./)(?!data/)(?!/app/)(?!data\\)",
    re.IGNORECASE | re.MULTILINE,
)

SENSITIVE_PROFILE_KEYWORDS = (
    "password_hash",
    "token_hash",
    "sessions",
    "receiver_name",
    "receiver_phone",
    "receiver_address",
)

BINARY_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".gz", ".tar", ".bz2", ".7z",
    ".duckdb", ".sqlite", ".db", ".parquet",
    ".xlsx", ".xls", ".docx",
    ".node", ".wasm",
    ".tsbuildinfo",
})

EXCLUDE_PATHS = (
    "tests/fixtures/",
    "tests/unit/test_audit_profile.py",
    "tests/unit/test_public_repo_scan.py",
    "tests/unit/test_privacy.py",
    "tests/unit/test_orders_adapter.py",
    "tests/unit/test_api.py",
    "src/ecom_insight/privacy/audit_profile.py",
    "src/ecom_insight/privacy/sanitizer.py",
    "src/ecom_insight/security/",
    "scripts/audit_public_repo.py",
    ".env.example",
    ".env.demo",
)


@dataclass(frozen=True, slots=True)
class Finding:
    file: str
    line: int
    rule: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.rule}"


def _git_tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        (root / line.strip())
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def _is_excluded(path: Path, root: Path) -> bool:
    rel = str(path.relative_to(root))
    if path.suffix.lower() in BINARY_EXTS:
        return True
    return any(rel.startswith(ex) or ex in rel for ex in EXCLUDE_PATHS)


def _scan_line(line: str) -> list[str]:
    rules: list[str] = []
    if ABSOLUTE_PATH_RE.search(line):
        rules.append("absolute_path")
    if PHONE_RE.search(line):
        rules.append("phone_number")
    if ID_CARD_RE.search(line):
        rules.append("id_card_number")
    if COOKIE_RE.search(line):
        rules.append("cookie_header")
    if AUTHORIZATION_RE.search(line):
        rules.append("authorization_header")
    if BEARER_RE.search(line):
        rules.append("bearer_token")
    if TOKEN_ASSIGNMENT_RE.search(line):
        rules.append("token_assignment")
    if PRIVATE_KEY_RE.search(line):
        rules.append("private_key")
    if ENV_SECRET_VALUE_RE.search(line):
        rules.append("env_secret_value")
    return rules


def _scan_json_profile(path: Path, root: Path) -> list[Finding]:
    rel = str(path.relative_to(root))
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    findings: list[Finding] = []
    for kw in SENSITIVE_PROFILE_KEYWORDS:
        if kw in content:
            for i, line in enumerate(content.splitlines(), 1):
                if kw in line:
                    findings.append(Finding(file=rel, line=i, rule=f"sensitive_profile_keyword:{kw}"))
    return findings


def scan_repository(root: Path | None = None) -> list[Finding]:
    root = (root or Path.cwd()).resolve()
    files = _git_tracked_files(root)
    findings: list[Finding] = []

    for path in files:
        if _is_excluded(path, root):
            continue
        rel = str(path.relative_to(root))

        if path.suffix == ".json" and "data_profile" in path.name:
            findings.extend(_scan_json_profile(path, root))
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for i, line in enumerate(content.splitlines(), 1):
            for rule in _scan_line(line):
                findings.append(Finding(file=rel, line=i, rule=rule))

    return findings


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(argv[0]).resolve() if argv else Path.cwd().resolve()
    findings = scan_repository(root)

    if not findings:
        print("No sensitive content found in tracked files.")
        return 0

    print(f"Found {len(findings)} potential issue(s):\n")
    for finding in findings:
        print(f"  {finding}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
