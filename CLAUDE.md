# Google Ads CLI — developer reference

Single-file Python CLI (`google_ads_cli.py`) using the official `google-ads`
library, API version pinned to **v24**. Phase 1 is read-only.

## Conventions
- Commands are `cmd_<name>(args)` functions wired in `build_parser()`; kebab-case
  subcommand names. Global flags: `--account`, `--json`.
- Auth is OAuth2 via `.env` → `_config_dict()` → `GoogleAdsClient.load_from_dict()`.
  Secrets live ONLY in `.env` (gitignored). Never hardcode credentials.
- Multi-account: env vars may carry an uppercase `_<NAME>` suffix; `_env()` resolves
  the named variant first, falling back to the base var.
- Money is in **micros** on the API (`_micros()` divides by 1e6). IDs may have
  dashes in the UI; `_clean_id()` strips them.

## Reads, quota & rate limits
- All reads go through `_run_query()` (uses `search_stream`). **A Search/SearchStream
  request = 1 operation regardless of rows** (confirmed against the API docs) — so
  `_run_query` tracks `1` op, NOT `len(rows)`. Quota state is per account/day in `.quota/`.
- Daily quota: Basic Access = 15,000 ops/day (reads + mutates combined); Standard Access
  = effectively unlimited. Cap is `GOOGLE_ADS_DAILY_OP_CAP` (default 15,000) — raise it for
  Standard Access tokens.
- **Enforcement is a hard stop, not just a warning.** `_quota_guard(account, n)` runs
  BEFORE each real call (reads: n=1; writes: n=len(ops), only when `--confirm`) and
  `_die`s if it would exceed the cap — so a runaway loop can't blow the daily budget.
  `_track_ops` still records usage and warns at 80%.
- **Per-second rate limits (QPS)** are separate and metered per CID + developer token.
  `_execute_with_retry()` wraps every read/mutate call: on `RESOURCE_EXHAUSTED` /
  `RESOURCE_TEMPORARILY_EXHAUSTED` (`_rate_error_retry_after` detects `quota_error` and
  reads Google's `retry_delay`) it backs off exponentially (5→10→20 s, or Google's
  suggested delay) up to 3 retries, then aborts. Non-rate errors still report + exit.
- The counter buckets by **Pacific date** via `_today()` (`GOOGLE_TZ = America/Los_Angeles`)
  to match Google's quota reset — change `_today()` if Google ever changes the reset tz.

## Adding a command
1. Write `cmd_<name>(args)` — build GAQL or a service request, call `_run_query()`
   or the service, format both `--json` and human output.
2. Register it in `build_parser()` with `set_defaults(func=cmd_<name>)`.

## Phase 2 (mutations) — design notes
- Mutations = 1 op each. Use `mutate_*` service methods with operation objects
  (`client.get_type("...Operation")`, `op.create`/`op.update`).
- Every mutation command must: (a) print a plan, (b) require `--confirm`, (c) track
  ops. Mirror the Sklik "plan before write" safety pattern.
- Search-campaign build order: budget → campaign (SEARCH) → ad group → RSA → keywords
  → geo/schedule criteria. RSA limits: 3–15 headlines (≤30 chars), 2–4 descriptions
  (≤90 chars); optional pinning.
- **Editing existing entities:** ads are mostly immutable. `ad-update-url` updates Final
  URL in place via `AdService.mutate_ads` (URL fields ARE mutable; text assets are NOT).
  To change ad text: `rsa-create` new + `ad-status … removed` old. **`ad-status removed`
  uses `op.remove` — a status update to REMOVED silently no-ops** (don't "fix" it back).
- `keyword-remove` takes `adGroupId~criterionId` fragments and builds the criterion
  resource name; `ad-status` builds `adGroupAds/{adGroupId}~{adId}` for the ad-group-ad.

## Key references (Google Ads API docs)
- Account hierarchy: `customer_client` GAQL + `CustomerService.list_accessible_customers`
- Reporting: `GoogleAdsService.search_stream` with GAQL
- Keyword research: `KeywordPlanIdeaService.generate_keyword_ideas`
- Search campaign creation: docs/campaigns/search-campaigns/getting-started
