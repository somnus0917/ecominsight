# Public Release Checklist

Before publishing or updating the EcomInsight repository, run every check below.
All commands are safe, read-only, and do not require real business data.

## 1. Sensitive content scan

```bash
uv run ecom-audit-public
```

Exit code **must** be 0. If findings appear, fix the source before committing.
The scanner checks Git-tracked files for:

- macOS / Linux / Windows absolute paths
- Mainland phone numbers and ID card numbers
- Cookie, Authorization and Bearer token headers
- API key / secret / token assignments
- Private key headers
- `.env` secret values (paths and booleans are allowed)
- Sensitive keywords in `artifacts/data_profile.json`

## 2. 绝对路径检查

第 1 步的 `ecom-audit-public` 已覆盖 macOS、Linux 和 Windows 的绝对路径检查。为避免把
敏感路径模式本身复制进公开文档，不再单独维护正则命令；该命令必须返回 0。

## 3. Full test suite

```bash
uv run pytest
uv run ruff check src tests scripts
uv run mypy src
```

## 4. Frontend checks

```bash
npm --prefix frontend run check
npm --prefix frontend run build
```

## 5. Demo build verification

```bash
uv run ecom-demo
```

Confirm `data/demo/processed/ecom_insight_demo.duckdb` exists and all fact
tables have `synthetic = true`.

## 6. Public audit profile

Verify `artifacts/data_profile.json` is the public-safe version:

```bash
uv run python -c "from ecom_insight.privacy import assert_public_profile_safe; import json; assert_public_profile_safe(json.load(open('artifacts/data_profile.json')))"
```

## 7. Git history spot-check

Review `docs/git_history_audit.md` for any unresolved high-risk items.

## 8. Screenshot provenance

All screenshots in `docs/assets/ui/` must originate from synthetic demo data.
If any screenshot needs replacement, run:

```bash
npm --prefix frontend run capture:demo
```

## 9. Documentation review

- README must lead with the 3-minute demo, not real-data paths.
- No document should describe synthetic evaluation results as real accuracy.
- `confidence` / `evidence_score` terminology must be consistent across docs.

## 10. Secrets and credentials

- `.env` must never be committed (already in `.gitignore`).
- `.env.example` and `.env.demo` must contain only placeholder or safe values.
- No API keys, tokens or passwords in any tracked file.
