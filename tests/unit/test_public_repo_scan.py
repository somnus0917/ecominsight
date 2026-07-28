from __future__ import annotations

from pathlib import Path

from ecom_insight.security.public_scan import Finding, _scan_line, scan_repository


def test_scan_line_detects_absolute_path() -> None:
    assert "absolute_path" in _scan_line("/Users/someone/secret")


def test_scan_line_detects_phone_number() -> None:
    assert "phone_number" in _scan_line("phone is 13800138000")


def test_scan_line_detects_private_key() -> None:
    assert "private_key" in _scan_line("-----BEGIN RSA PRIVATE KEY-----")


def test_scan_line_detects_env_secret() -> None:
    assert "env_secret_value" in _scan_line("ECOM_LLM_API_KEY=sk-abc123def456")


def test_scan_line_ignores_env_path() -> None:
    assert "env_secret_value" not in _scan_line("ECOM_OUTPUT_ROOT=data/processed")


def test_scan_line_ignores_env_boolean() -> None:
    assert "env_secret_value" not in _scan_line("ECOM_EXTERNAL_API_ENABLED=false")


def test_scan_repository_finds_planted_secret(tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
    bad_file = repo / "config.py"
    bad_file.write_text('API_KEY = "sk-deadbeef12345678"\nPRIVATE_KEY_PATH = "/Users/leak/key.pem"\n')
    subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "test"],
        cwd=str(repo),
        capture_output=True,
        check=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )
    findings = scan_repository(repo)
    rules = {f.rule for f in findings}
    assert "absolute_path" in rules


def test_scan_repository_returns_empty_on_clean_repo() -> None:
    findings = scan_repository(Path(__file__).resolve().parent.parent.parent)
    assert findings == []


def test_finding_format() -> None:
    f = Finding(file="config.py", line=10, rule="absolute_path")
    assert str(f) == "config.py:10: absolute_path"
