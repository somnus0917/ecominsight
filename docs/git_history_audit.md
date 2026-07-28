# Git History Audit

**Audit date:** 2026-07-28
**Method:** `git log --all --diff-filter=A --name-only` plus content inspection of
historical versions of key files.
**Scope:** All commits reachable from all refs.

## Method

1. Enumerated every file ever added to any commit.
2. Filtered for sensitive extensions: `.env`, `.db`, `.sqlite`, `.duckdb`,
   `.csv`, `.parquet`, `.xlsx`, `*cookie*`, `*token*`, `*credential*`,
   `*login*`, `*screenshot*`, `*storage_state*`.
3. Inspected historical content of `artifacts/data_profile.json` and
   `.playwright-cli/` files for absolute paths, auth table structures and
   personal information.
4. Checked whether `.env` was ever committed.

## Findings

### 1. Absolute path in historical `artifacts/data_profile.json`

- **Commits:** `741e3b7`, `8d4109a`
- **Content:** a local absolute source-snapshot path (redacted as `<LOCAL_SNAPSHOT_ROOT>`)
- **Risk:** Low — a local filesystem path, not a secret or credential.
- **Status:** Fixed in current HEAD (Phase A1). Historical commits still
  contain the path.
- **Recommendation:** If path disclosure is unacceptable, run
  `git filter-repo --replace-text` with a replacements file mapping the
  absolute path to `<LOCAL_SNAPSHOT_ROOT>`. This rewrites history and requires
  a force-push. **Do not execute without explicit authorization.**

### 2. Authentication table structures in historical `artifacts/data_profile.json`

- **Commits:** `741e3b7`, `8d4109a`, and all intermediate commits until Phase A2.
- **Content:** Table names (`sessions`, `users`, `app_kv`) and column names
  (`token_hash`, `password_hash`, `username`) were present in the public
  audit profile.
- **Risk:** Low — structural metadata only; no values, tokens or hashes were
  ever committed.
- **Status:** Fixed in current HEAD (Phase A2). Historical commits still
  contain the structures.
- **Recommendation:** Same as finding 1 — history rewrite if required.

### 3. Playwright CLI artifacts

- **Commits:** `8c2133b`, `726ba69` (added); removed in a later commit.
- **Files:** `.playwright-cli/console-*.log`, `.playwright-cli/page-*.yml`,
  `.playwright-cli/page-*.png`.
- **Content inspected:** Console logs contain React DevTools messages and
  404 errors. Page YAML contains UI accessibility tree structure (navigation
  labels, URLs). No business data, PII or credentials were found in the
  text files.
- **Risk:** Low — developer tooling output, no sensitive content detected.
- **Status:** Files are no longer tracked. `.gitignore` now excludes
  `.playwright-cli/`.
- **Recommendation:** No action needed. If desired, the blobs can be removed
  with `git filter-repo --path .playwright-cli/ --invert-paths`.

### 4. UI screenshots in `docs/assets/ui/`

- **Commits:** `3429fe1`, `8c2133b`, `726ba69`.
- **Files:** `overview.png`, `overview-mobile.png`, `anomaly-detail.png`.
- **Content:** PNG images of the operations console. These were captured
  from the local development environment and may display data derived from
  the real business snapshot (shop names are HMAC-masked, but amounts and
  metric values are real-derived).
- **Risk:** Medium — real business-derived metrics may be visible. No direct
  PII (names, phones, addresses) is shown in the UI, but financial figures
  are real.
- **Status:** Phase A5 will replace these with synthetic-data screenshots.
  Until replacement, these should not be used in public portfolio materials.
- **Recommendation:** After `npm --prefix frontend run capture:demo` succeeds
  and synthetic screenshots are verified, overwrite the existing files. If
  the old screenshots must be purged from history, use
  `git filter-repo --path docs/assets/ui/ --invert-paths` (requires
  authorization and force-push).

### 5. `.env` file

- **Status:** Never committed. `.gitignore` has always excluded `.env`.
- **Risk:** None.

### 6. Real data files (`.db`, `.sqlite`, `.duckdb`, `.csv`, `.parquet`)

- **Status:** Never committed. `.gitignore` excludes all these extensions.
- **Risk:** None.

### 7. Cookies, tokens, private keys

- **Status:** Never found in any tracked file or historical commit.
- **Risk:** None.

## Summary

| # | Finding | Risk | Current Status |
|---|---------|------|---------------|
| 1 | Absolute path in historical data_profile.json | Low | Fixed in HEAD; remains in history |
| 2 | Auth table structures in historical data_profile.json | Low | Fixed in HEAD; remains in history |
| 3 | Playwright CLI artifacts in history | Low | Untracked; in history only |
| 4 | UI screenshots from real data | Medium | To be replaced by Phase A5 |
| 5 | `.env` committed | None | Never committed |
| 6 | Real data files committed | None | Never committed |
| 7 | Credentials in history | None | Not found |

## Action required

No action is required for items 5–7. For items 1–4, the current HEAD is
safe. If the repository has already been pushed publicly, consider whether
the historical exposure of the absolute path (item 1) and the real-data
screenshots (item 4) warrant a history rewrite. **History rewrite requires
explicit authorization and must use `git filter-repo`, not `git reset`.**
