# Google Ads CLI

Read-only foundation (Phase 1) for managing **search** campaigns on Google Ads —
reporting, keyword research, and account inspection. Modeled on the Sklik tooling:
a mechanical CLI driven by a strategic skill.

**Scope:** search campaigns, keyword research, optimization, + DSA / RLSA / Smart
Bidding / conversions. Display, YouTube, App, Shopping, and Performance Max are
intentionally out of scope.

## Setup

```bash
./setup.sh                # venv + deps + .env from template
# edit .env: fill GOOGLE_ADS_DEVELOPER_TOKEN and GOOGLE_ADS_CLIENT_SECRET
./run.sh auth             # opens browser → prints a refresh token
# paste GOOGLE_ADS_REFRESH_TOKEN into .env
./run.sh accounts         # first live read
```

You need four credentials in `.env` (see `.env.example`):
developer token, OAuth client id + secret, refresh token, and the MCC login
customer id (`1379904327`).

## Commands (Phase 1 — read-only)

| Command | What it does |
|---------|--------------|
| `auth` | One-time OAuth flow → refresh token |
| `accounts` | List accounts under the MCC |
| `campaigns <id> [--status]` | List search campaigns |
| `query <id> --gaql "..."` | Run an arbitrary GAQL query (reporting core) |
| `report <id> --entity campaign|ad_group|keyword --from --to` | Preset performance report |
| `keywords-research <id> --seed "ai kurz,vibe coding"` | Keyword Planner ideas |
| `search-terms <id> --from --to` | Real search queries (source for negatives) |
| `quota` | Today's operation usage vs daily cap |

All read commands accept `--json` and `--account <name>`.

## Commands (Phase 2 — write / mutations)

**Every mutation defaults to dry-run** (the API's `validate_only` — validates but
writes nothing) and prints a plan. Add `--confirm` to actually write.

| Command | What it does |
|---------|--------------|
| `campaign-status <cid> <campaign_id> --status enabled|paused|removed` | Enable / pause / remove a campaign |
| `budget-set <cid> <campaign_id> --amount <czk>` | Set a campaign's daily budget |
| `bidding-set <cid> <campaign_id> --strategy ... [--target-cpa] [--target-roas]` | Switch bidding strategy |
| `campaign-create <cid> --name --budget [--bidding]` | Create a SEARCH campaign + budget (PAUSED) |
| `ad-group-create <cid> --campaign --name [--cpc]` | Create an ad group |
| `rsa-create <cid> --ad-group --headlines "a|b|c" --descriptions "x|y" --final-url` | Create a responsive search ad |
| `keyword-add <cid> --ad-group --keywords-json '[...]'` | Batch-add positive keywords |
| `negative-add <cid> --ad-group|--campaign --keywords "a,b" --match-type` | Add negative keywords |
| `ad-update-url <cid> <ad_id> --final-url <url>` | Change Final URL on an existing ad (keeps history) |
| `keyword-remove <cid> --criteria "adGroupId~criterionId,..."` | Remove keyword criteria |
| `ad-status <cid> <ad_group_id> <ad_id> --status enabled\|paused\|removed` | Enable/pause/remove a single ad |

Bidding strategies: `manual_cpc`, `max_conversions`, `max_conversion_value`,
`target_cpa` (needs `--target-cpa`), `target_roas` (needs `--target-roas`).

## Quota

Basic Access = **15,000 operations/day**. Reads can consume quota quickly (large
reports), so every read is tracked locally in `.quota/` and warns at 80% and 100%.
The read-op count is a conservative proxy (returned rows); mutations count 1/op;
dry-runs (validate-only) are not counted. The counter buckets by the **Pacific date**
(`America/Los_Angeles`) to match Google's quota reset — it's a local estimate, not
Google's server count (see Cloud Console → API dashboard for the real number). Cap is
configurable via `GOOGLE_ADS_DAILY_OP_CAP`.

## Roadmap

- **Phase 1 (read):** ✅ done — reporting, keyword research, account inspection.
- **Phase 2 (write):** ✅ done — campaign / ad group / RSA / keyword / negative /
  budget / bidding (tCPA, tROAS, Max conv) with dry-run-by-default + `--confirm`.
- **Phase 3 (strategy):** DSA setup, RLSA audience attach, ad-schedule & geo
  criteria, conversion-action management. *(next)*
- **Skill:** `google-ads` skill as the strategic layer (campaign structure, RSA
  rules, keyword clustering, optimization playbooks). *(next)*
