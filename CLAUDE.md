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

## Reads & quota
- All reads go through `_run_query()` (uses `search_stream`) which counts returned
  rows into `_track_ops()`. Quota state is per account/day in `.quota/`.
- Basic Access = 15,000 ops/day. Row-count is a conservative proxy for read ops;
  refine `_track_ops` once exact counting is confirmed against the live API.
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
