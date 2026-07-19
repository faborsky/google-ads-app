# Google Ads App — CLI for the Google Ads API

Python CLI for managing Google Ads **search** campaigns via the official `google-ads` library (API pinned to **v24**). Built to be driven by a human **and** by Claude Code: structured `--json` I/O, validate-only dry-runs by default, and a self-enforcing daily operation budget.

## Setup

```bash
./run.sh <command> [flags]
# or: source .venv/bin/activate && python google_ads_cli.py <command> [flags]
```

## Code structure

The implementation is a package under `gads/`; `google_ads_cli.py` is a thin entrypoint.

- `gads/api.py` — **engine**: `.env` config + multi-account resolution (`_env` suffixes), client factory (API version pin), the **daily quota guard** (`.quota/`, Pacific-date bucketing, hard stop BEFORE the cap), QPS retry with back-off (`_execute_with_retry`), `_run_query` (search_stream, 1 op/request), `_run_mutation` (validate-only default), `_require_paused_before_remove` (the no-undelete brake).
- `gads/formatting.py` — micros⇄CZK, JSON output, `_die`/`_err`, `_row_to_dict`.
- `gads/lint.py` — **preflight lint**: RSA/asset text limits (hard fail) + editorial-policy style checks (warnings) BEFORE any API call.
- `gads/commands/*.py` — one module per domain (`account`, `pulse`, `reporting`, `research`, `campaigns`, `groups`, `ads`, `keywords`, `budgets`, `targeting`, `assets`, `audiences`, `sharedsets`, `labels`, `conversions`, `recommendations`, `dsa`, `pmax`, `experiments`, `auth`).
- `gads/cli.py` — argparse wiring via `_cmd()` (one call = parser + handler → parity by construction).

No shared mutable module state — commands take everything from `args`; quota state lives in `.quota/` files. `BASE_DIR` in `api.py` resolves to the repo root so `.env` and `.quota/` stay put.

## Authentication & accounts

OAuth2 via `.env`: developer token + OAuth client id/secret + refresh token + MCC `login_customer_id`. Multi-account via env suffixes (`GOOGLE_ADS_REFRESH_TOKEN_<NAME>` → `--account <name>`); `_env()` resolves named variant first. Target customer ID is a positional arg (dashes stripped by `_clean_id`). Money is **micros** on the API (`_micros`/`_to_micros` convert).

## Commands (85, grouped)

**Full flag reference + examples: [README.md](README.md).** Index:

- **Setup/account:** `auth`, `accounts`, `quota`, `api-limits`
- **Overview:** `pulse` (5-op account digest: totals+deltas+movers+opt score+recommendations+policy problems — run FIRST for any review)
- **Reporting:** `query`, `report`, `changes` (`--sweep`)
- **Campaigns:** `campaigns`, `campaign-create` (PAUSED, geo+language defaults), `campaign-status`, `bidding-set`, `campaign-targeting`
- **Budgets:** `budgets`, `budget-set`, `budget-create` (shared), `budget-assign`, `budget-remove`
- **Groups/ads:** `ad-groups`, `ad-group-create`, `ads`, `rsa-create` (lint + ` @H1` pinning), `ad-status`, `ad-update-url`, `ad-policy`
- **Keywords:** `keywords`, `keyword-add`, `keyword-remove`, `negative-add`
- **Shared sets:** `shared-sets`, `shared-set-create/add/keywords/remove-keywords/attach/remove`, `customer-negatives-attach/detach`
- **Assets:** `assets`, `asset-links`, `sitelink-create`, `callout-create`, `snippet-create`, `asset-link`, `asset-unlink`
- **Audiences:** `audiences`, `audience-create`, `audiences-attached`, `audience-attach` (`--mode`), `audience-exclude`, `audience-detach`
- **Targeting:** `geo-suggest`, `geo-target`, `language-target`, `schedule-set`, `device-bid`, `demographics`, `demographic-target`
- **Conversions:** `conversions`, `conversion-create`, `conversion-update`
- **Recommendations:** `recommendations`, `recommendation-apply`, `recommendation-dismiss`
- **Research:** `keywords-research` (1 QPS!), `search-terms`
- **Labels:** `labels`, `label-create`, `label-assign`, `label-unassign`, `label-remove`
- **DSA:** `dsa-setting`, `dsa-ad-group-create`, `dsa-create`, `webpage-targets`, `webpage-target-add`, `webpage-target-remove`
- **PMax (reporting only):** `pmax`, `pmax-search-terms`
- **Experiments:** `experiments`, `experiment-create`, `experiment-schedule`, `experiment-results`, `experiment-end`, `experiment-promote`

## Safety

- **Every mutation defaults to `validate_only` dry-run** + printed plan; `--confirm` writes. Dry-runs don't count toward quota.
- **Quota guard is a hard stop, not a warning**: `_quota_guard` runs BEFORE each real call and dies if it would exceed `GOOGLE_ADS_DAILY_OP_CAP` (default 15 000 = Basic Access; Search/SearchStream request = 1 op regardless of rows). Counter buckets by **Pacific date** (Google's reset). `_track_ops` records + warns at 80 %.
- **QPS retry**: `RESOURCE_EXHAUSTED`/`_TEMPORARILY_` → back-off 5→10→20 s (honours Google's `retry_delay`), max 3 retries, then abort. Never loop-retry manually on top.
- **Preflight lint** (`gads/lint.py`) blocks count/length violations and warns on editorial-policy style issues before any API call.
- Parse programmatic output with `--json`.

## ⚠️ Critical for automation (read before scripting writes)

- **REMOVED is PERMANENT** — no undelete in Google Ads. The CLI refuses to remove non-PAUSED campaigns/ads (`--force` overrides). REMOVED entities stay in API listings forever (default filters hide them).
- **Ad text is immutable** — only Final URL updates in place (`ad-update-url`). Text change = `rsa-create` new + `ad-status … removed` old. A status *update* to REMOVED silently no-ops (the CLI uses a remove operation — don't "fix" it back). `AdGroupAdService` silently ignores non-status fields on update — no error, just a no-op.
- **Assets are create-only** — no edit/delete, only link management (`asset-link`/`asset-unlink`). Duplicates silently merge.
- **A campaign without geo/language criteria serves WORLDWIDE** — `campaign-create` sets CZ+cs defaults; verify with `campaign-targeting`.
- **Positive audience criteria**: campaign XOR ad-group level (not both); `--mode targeting` NARROWS serving, `observation` doesn't.
- **`changes`** requires date window (event ≤30 d, sweep ≤90 d) + LIMIT ≤10k — CLI enforces.
- **Recommendations' resource names go stale daily** — list and apply/dismiss in one session. Apply/dismiss have NO validate_only (dry-run = plan only).
- **GAQL**: no `LAST_90_DAYS` literal (use BETWEEN); `--json` rows are camelCase (`MessageToDict`).
- **`metrics.conversions` = primary actions only**; `all_conversions` = everything. `pulse` warns when primary is 0 but all isn't (measurement misconfig).
- **Keyword Planner = 1 QPS** — sequential requests only.

Full API behaviour, quirks and limits: **[docs/api-notes.md](docs/api-notes.md)**.

## Release checklist

Bump `__version__` in `gads/__init__.py` → update README (version line + command tables), CLAUDE.md (command count/index), CHANGELOG.md (new `## [x.y.z] — YYYY-MM-DD` entry), bundled skill → run `python scripts/check_docs_consistency.py` (must pass) → commit → tag `vX.Y.Z`. (GitHub Release až po zveřejnění repa.)

## Documentation map

- **[README.md](README.md)** — full command reference, flags, auth walkthrough, worked examples (Czech).
- **[docs/api-notes.md](docs/api-notes.md)** — how the Google Ads API actually behaves (versions, quotas, immutability, quirks).
- **[CHANGELOG.md](CHANGELOG.md)** — version history.
- **`skill/google-ads/`** — the bundled Claude Code skill (`/google-ads`): scenarios, safety rules, RSA/structure references. Install: `skill/INSTALL.md`.
