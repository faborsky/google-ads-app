# Google Ads App — CLI for the Google Ads API

Python CLI for managing Google Ads **search** campaigns via the official `google-ads` library (API pinned to **v25**, library 31.4+). Version 2.2.0, 85 commands. Built to be driven by a human **and** by Claude Code: structured `--json` I/O, validate-only dry-runs by default, and a self-enforcing daily operation budget. Czech user docs in [README.md](README.md).

## Setup

```bash
./run.sh <command> [flags]
# or: source .venv/bin/activate && python google_ads_cli.py <command> [flags]
```

## Code structure

The implementation is a package under `gads/`; `google_ads_cli.py` is a thin entrypoint.

- `gads/api.py` — **engine**: `.env` config + multi-account resolution (`_env` suffixes), two auth modes (installed-app OAuth refresh token **or** service account via `GOOGLE_ADS_JSON_KEY_FILE_PATH`), client factory with clean auth errors (`_get_client`: invalid_grant/invalid_client → actionable message, never a traceback), the **sliding-24 h quota guard** (`.quota/<account>.json` event log, hard stop BEFORE the cap), QPS retry with back-off (`_execute_with_retry`; transient transport errors retried for reads only), `_run_query` (search_stream, 1 op/request), `_run_mutation` (validate-only default, dry-runs counted too), **presence-aware `_field_mask`**, `_require_paused_before_remove` (the no-undelete brake), `_atomic_write_text`.
- `gads/formatting.py` — micros⇄CZK, JSON output, `_die`/`_err`, `_row_to_dict`.
- `gads/lint.py` — **preflight lint**: RSA/asset text limits (hard fail) + editorial-policy style checks (warnings) BEFORE any API call.
- `gads/commands/*.py` — one module per domain (`account`, `pulse`, `reporting`, `research`, `campaigns`, `groups`, `ads`, `keywords`, `budgets`, `targeting`, `assets`, `audiences`, `sharedsets`, `labels`, `conversions`, `recommendations`, `dsa`, `pmax`, `experiments`, `auth`).
- `gads/cli.py` — argparse wiring via `_cmd()` (one call = parser + handler → parity by construction; `--json` accepted before AND after the subcommand).
- `tests/` — offline pytest suite (no credentials, no network): a real `GoogleAdsClient` on v25 stubs with fake credentials + a recorder replacing the gRPC service methods, so every write command's operations are validated against the actual API types. `venv: python -m pytest tests/`; dev deps in `requirements-dev.txt`.
- `scripts/check_docs_consistency.py` — CLI ↔ README ↔ CLAUDE.md ↔ skill consistency gate.

No shared mutable module state — commands take everything from `args`; quota state lives in `.quota/` files. `BASE_DIR` in `api.py` resolves to the repo root so `.env` and `.quota/` stay put.

## Authentication & accounts

Two modes, both from `.env` (see README → Autentizace for the walkthrough):
- **Installed-app OAuth2**: developer token + OAuth client id/secret + refresh token + MCC `login_customer_id`. `./run.sh auth` runs the browser flow and **writes the refresh token into `.env`** (atomic, 600; `--print` to show instead). OAuth consent screen must be **In production** — in Testing mode refresh tokens expire after 7 days (`invalid_grant`). The consent screen now lives under **Google Auth Platform** (`console.cloud.google.com/auth/audience` for publishing status, `/auth/clients` for the Desktop-app client), not the old "APIs & Services → OAuth consent screen" path.
- **Service account**: `GOOGLE_ADS_JSON_KEY_FILE_PATH` (+ optional `GOOGLE_ADS_IMPERSONATED_EMAIL`); the SA e-mail is added as a user of the Google Ads/MCC account. No browser, no expiry — preferred for automations. The library picks the flow by which keys are PRESENT, so `_config_dict` omits the unused trio.

Multi-account via env suffixes (`GOOGLE_ADS_REFRESH_TOKEN_<NAME>` → `--account <name>`); `_env()` resolves named variant first. Target customer ID is a positional arg (dashes stripped by `_clean_id`). Money is **micros** on the API (`_micros`/`_to_micros` convert).

Developer-token access levels matter: **Explorer Access** (the usual default after sign-up) serves production accounts with 2 880 ops/day but **blocks KeywordPlanIdeaService** (`keywords-research` fails until Basic Access); **Basic Access** = 15 000 ops/day, everything.

## Commands (85, grouped)

**Full flag reference + examples: [README.md](README.md).** Index:

- **Setup/account:** `auth`, `accounts`, `quota`, `api-limits`
- **Overview:** `pulse` (5-op account digest: totals+deltas+movers+opt score+recommendations+policy problems — run FIRST for any review)
- **Reporting:** `query`, `report`, `changes` (`--sweep`, `--limit`)
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
- **Research:** `keywords-research` (1 QPS! Basic Access), `search-terms`
- **Labels:** `labels`, `label-create`, `label-assign`, `label-unassign`, `label-remove`
- **DSA:** `dsa-setting`, `dsa-ad-group-create`, `dsa-create`, `webpage-targets`, `webpage-target-add`, `webpage-target-remove`
- **PMax (reporting only):** `pmax`, `pmax-search-terms` (`--limit` trims with a notice)
- **Experiments:** `experiments`, `experiment-create`, `experiment-schedule`, `experiment-results`, `experiment-end`, `experiment-promote`

## Safety

- **Every mutation defaults to `validate_only` dry-run** + printed plan; `--confirm` writes. Dry-runs are counted toward the local quota estimate (Google doesn't document an exemption → conservative).
- **Quota guard is a hard stop, not a warning**: `_quota_guard` runs BEFORE each real call and dies if it would exceed `GOOGLE_ADS_DAILY_OP_CAP` (default 15 000 = Basic Access; set 2880 on Explorer Access; Search/SearchStream request = 1 op regardless of rows). Usage is a **sliding 24 h window** per account (`.quota/<account>.json`), matching how Google meters the limit. `_track_ops` records + warns at 80 %.
- **QPS retry**: `RESOURCE_EXHAUSTED`/`_TEMPORARILY_` → back-off 5→10→20 s (honours Google's `retry_delay`), max 3 retries, then abort. Transient transport errors (UNAVAILABLE/DEADLINE_EXCEEDED/INTERNAL) are retried for reads only — a write may have landed, it is never replayed. Never loop-retry manually on top.
- **Preflight lint** (`gads/lint.py`) blocks count/length violations and warns on editorial-policy style issues before any API call.
- **Listings never truncate silently**: GAQL listings carry no `LIMIT` (search_stream pages itself); the only API-mandated LIMIT (`changes`) warns when the result hits it; `--limit` flags trim with a stderr notice.
- Parse programmatic output with `--json`.

## ⚠️ Critical for automation (read before scripting writes)

- **REMOVED is PERMANENT** — no undelete in Google Ads. The CLI refuses to remove non-PAUSED campaigns/ads (`--force` overrides). REMOVED entities stay in API listings forever (default filters hide them).
- **Ad text is immutable** — only Final URL updates in place (`ad-update-url`). Text change = `rsa-create` new + `ad-status … removed` old. A status *update* to REMOVED silently no-ops (the CLI uses a remove operation — don't "fix" it back). `AdGroupAdService` silently ignores non-status fields on update — no error, just a no-op.
- **Update masks must be presence-aware.** `protobuf_helpers.field_mask(None, msg)` diffs values against defaults, so `primary_for_goal = False`, `bid_modifier = 0`, an empty `manual_cpc`/`maximize_conversions` bidding message… vanish from the mask and the API performs a **silent no-op** (this shipped undetected until 2.2.0). And a mask may NOT name an empty message field either (`FIELD_HAS_SUBFIELDS`) — the documented workaround is naming one mutable subfield (e.g. `maximize_conversions.target_cpa_micros`; never `cpc_bid_ceiling/floor` — portfolio-only). Always build masks with `api._field_mask()` (recursive `ListFields()` walk + `_EMPTY_MESSAGE_LEAF` map), and when adding an update command, write a test asserting the path is in the mask.
- **Assets are create-only** — no edit/delete, only link management (`asset-link`/`asset-unlink`). Duplicates silently merge.
- **A campaign without geo/language criteria serves WORLDWIDE** — `campaign-create` sets CZ+cs defaults; verify with `campaign-targeting`.
- **Positive audience criteria**: campaign XOR ad-group level (not both); `--mode targeting` NARROWS serving, `observation` doesn't.
- **`changes`** requires date window (event ≤30 d, sweep ≤90 d) + LIMIT ≤10k — CLI enforces and warns on truncation.
- **Recommendations' resource names go stale daily** — list and apply/dismiss in one session. Apply/dismiss have NO validate_only (dry-run = plan only).
- **GAQL**: no `LAST_90_DAYS` literal (use BETWEEN); `--json` rows are camelCase (`MessageToDict`).
- **`metrics.conversions` = primary actions only**; `all_conversions` = everything. `pulse` warns when primary is 0 but all isn't (measurement misconfig).
- **Keyword Planner = 1 QPS** and needs Basic Access — sequential requests only.
- **Never add a hardcoded `LIMIT` to a listing** — search_stream returns everything; a fixed LIMIT truncates bigger accounts silently (the Sklik app shipped that class of bug; `pmax-search-terms` had `LIMIT 500` until 2.2.0).

Full API behaviour, quirks and limits: **[docs/api-notes.md](docs/api-notes.md)**.

## Release checklist

Bump `__version__` in `gads/__init__.py` → update README (version line + 🆕 section + command tables), CLAUDE.md (command count/index), CHANGELOG.md (new `## [x.y.z] — YYYY-MM-DD` entry), bundled skill → run `python scripts/check_docs_consistency.py` (must pass) → run `python -m pytest tests/` (must pass) → commit → tag `vX.Y.Z` → **GitHub Release from the tag** (`gh release create vX.Y.Z --latest --title "vX.Y.Z — <changelog headline>"`, notes = the CHANGELOG entry). A pushed tag alone does NOT show on /releases and subscribers get no notification — the release step is mandatory. (GitHub Release až po zveřejnění repa; MIT LICENSE + sekce „Licence" v README přidány ve 2.2.0.)

## Documentation map

- **[README.md](README.md)** — full command reference, flags, auth walkthrough (access levels, OAuth vs service account), worked examples (Czech).
- **[docs/api-notes.md](docs/api-notes.md)** — how the Google Ads API actually behaves (versions, access levels, quotas, immutability, quirks).
- **[CHANGELOG.md](CHANGELOG.md)** — version history.
- **`skill/google-ads/`** — the bundled Claude Code skill (`/google-ads`): scenarios, safety rules, RSA/structure references. Install: `skill/INSTALL.md`.
