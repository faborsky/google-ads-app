# Google Ads App

**🇬🇧 English** · [🇨🇿 Čeština](README.cs.md) · [🇪🇸 Español](i18n/README.es.md) · [🇧🇷 Português](i18n/README.pt-BR.md) · [🇩🇪 Deutsch](i18n/README.de.md) · [🇫🇷 Français](i18n/README.fr.md) · [🇨🇳 简体中文](i18n/README.zh-CN.md) · [🇯🇵 日本語](i18n/README.ja.md) · [🇸🇪 Svenska](i18n/README.sv.md) · [🇳🇴 Norsk](i18n/README.nb.md) · [🇩🇰 Dansk](i18n/README.da.md)

A CLI for managing **Google Ads search campaigns** through the official [Google Ads API](https://developers.google.com/google-ads/api) (v25, `google-ads` library 35+). For marketers and founders who want to run campaigns from the terminal, or hand them to Claude Code, instead of clicking through the Google Ads web interface.

It covers the whole lifecycle of a search campaign: campaigns, ad groups, RSA ads, keywords, negatives (including shared lists), assets (sitelinks/callouts/snippets), audiences and remarketing, targeting (geo/language/schedule/device/demographics), budgets, Smart Bidding, conversion actions, Google's recommendations, ad approval checks, change history, experiments and GAQL reporting. It does not handle Display/YouTube/Shopping; Performance Max is reporting only.

Author: [Jindřich Fáborský](https://www.faborsky.com)

> [!TIP]
> **The app is free and it's yours.** Clone it, use it, rebuild it your way.
>
> Want to build tools like this for your own marketing? That's what I teach: **[faborsky.com](https://www.faborsky.com)**.

The repo also ships a [Claude Code skill](#claude-code-skill-google-ads) that wraps the app.

## 🆕 What's new

Current version **2.3.0**: **no developer token needed any more** (Google sunset developer tokens on 2026-09-09; the access level now belongs to your Cloud project, the setup guide below is rewritten for it), library 35 (API stays on v25), `bidding-set --portfolio` attaches a campaign to a portfolio bid strategy, `campaign-create --no-search-partners` / `--presence-only`, **Windows** fixes (Git Bash venv, UTF-8 output through a pipe) and clearer errors for Explorer access and new accounts under an MCC. Thanks to the contributors who reported and sent these.

2.2.0, the **pre-release audit**: API moved to **v25** (library 31.4), **fixed silent no-op updates** (`bidding-set max_conversions`/`manual_cpc`, `device-bid --modifier 0` and `conversion-update --primary no` used to do nothing, because the update mask dropped fields set to their default value), **quota measured over a sliding 24 h window** (the way Google measures it, not by calendar day), `./run.sh auth` **writes the refresh token straight into `.env`** (the token no longer passes through the terminal or a chat), **service account** as an alternative to OAuth (no browser, no 7-day expiry), clean error messages instead of tracebacks (expired token, unapproved developer token…), `--json` also works after the command, no more hardcoded `LIMIT 500` in `pmax-search-terms`, an **offline test suite (107 tests)** that validates every write against the real API v25 types, MIT license. Before that, 2.1.0 (visual signature) and 2.0.0 (big refresh, 19 → **85 commands**). Full history: **[CHANGELOG.md](CHANGELOG.md)**.

> 💡 Want to hear about new versions? On GitHub: **Watch → Custom → Releases**.

## Two ways to use the app

**A) Orchestrated by Claude Code (the default and the easiest).** Claude Code (or another coding agent) drives the app through the bundled skill. You state goals in plain language, the agent calls the CLI, follows the safety rules (plan → approval → write, dry-run by default, quotas, "REMOVED is permanent") and knows the API's quirks. Fastest start: open Claude Code and paste a prompt like:

> *Clone https://github.com/faborsky/google-ads-app, run `./setup.sh`, install the bundled skill following `skill/INSTALL.md`, then walk me through getting the credentials into `.env` following the README (Authentication section).*

Claude sets everything up; **the credentials then go into `.env` only** (it's in `.gitignore`; never paste them into a chat or into code). From then on, `/google-ads` works from any project. Details: [skill/INSTALL.md](skill/INSTALL.md).

**B) Your own automations and agents (advanced).** The app is an ordinary CLI built to be driven by machines: `--json` output, mutations default to a validate-only dry-run, a built-in quota guard (you can't burn through the daily limit by accident) and QPS retry with back-off. Use it in your own scripts, crons or agent workflows. The full command reference is below, and API behaviour (quirks, limits) is in [docs/api-notes.md](docs/api-notes.md). For unattended runs use a **service account** (see [Authentication](#authentication)); it has nothing that expires.

## Requirements

- Python 3.10–3.14 (the `google-ads` library doesn't support 3.15 yet)
- A Google Ads account + API credentials (see below; it's more involved than for most APIs, but you only do it once)

## Installation

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

A Python other than the default `python3`: `PYTHON=python3.12 ./setup.sh`.

### Windows

The `setup.sh`/`run.sh` scripts are bash. On Windows, use **Git Bash** (part of [Git for Windows](https://git-scm.com/download/win)) or **WSL**; the scripts find the venv in both `.venv/bin` and `.venv/Scripts`. On Windows `python3` is often just a Microsoft Store alias, so run setup as `PYTHON=python ./setup.sh`. The CLI always writes UTF-8, so piped output (the way Claude Code reads it) keeps Czech diacritics and arrows intact. Or plain PowerShell:

```powershell
git clone https://github.com/faborsky/google-ads-app.git; cd google-ads-app
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # fill in the credentials
python google_ads_cli.py auth
python google_ads_cli.py accounts
```

## Authentication

The Google Ads API has the strictest access requirements of the big ad APIs: you need an approved **access level for your Google Cloud project** (= "you may call the API"), **OAuth access to the account** (= "you may touch these accounts") and an **MCC ID**. All of it is one-off. Checked against the official documentation on 2026-11-01 ([access levels](https://developers.google.com/google-ads/api/docs/api-policy/access-levels), [developer token sunset](https://developers.google.com/google-ads/api/docs/api-policy/developer-token)).

> **Developer tokens are gone.** Google sunset them on **2026-09-09**: the access level (Explorer / Basic / Standard) now belongs to the Cloud project and the API ignores the token. Since 2.3.0 the app doesn't need `GOOGLE_ADS_DEVELOPER_TOKEN`; an old value in `.env` does no harm.

### Overview: what goes into `.env`

You fill in three values by hand, the app writes the fourth itself, and **one number doesn't belong in `.env` at all**:

| Variable | What it is | Where to get it | How it gets there |
|---|---|---|---|
| `GOOGLE_ADS_CLIENT_ID` | OAuth client, ends with `.apps.googleusercontent.com` | Google Cloud Console (step 2) | you copy it by hand |
| `GOOGLE_ADS_CLIENT_SECRET` | that OAuth client's secret | Google Cloud Console (step 2) | you copy it by hand |
| `GOOGLE_ADS_REFRESH_TOKEN` | long-term access to your Google account | `./run.sh auth` (step 3) | **written automatically**, you never copy it anywhere |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | MCC ID **without dashes** (`123-456-7890` → `1234567890`) | Google Ads header (step 4) | you copy it by hand |
| `GOOGLE_ADS_DAILY_OP_CAP` | cap on operations per 24 h | depends on the Cloud project's access level (step 1) | `15000` (Basic) / `2880` (Explorer) |
| (none) | **customer ID of the target account** you're working on | `./run.sh accounts` | **doesn't go into `.env`**, it's a command argument |

Three numbers that are easy to mix up: **Client ID** (long string from Cloud) × **MCC login customer ID** (10 digits, goes into `.env`) × **client account customer ID** (10 digits, goes into the command).

An alternative to steps 2+3 without a browser: a **service account** (below).

### 0) Passkey: do this before you start

Since **2026-08-05** Google asks for passkey verification when you generate a new refresh token (step 3). Existing tokens aren't affected.

Check **[myaccount.google.com/signinoptions/passkeys](https://myaccount.google.com/signinoptions/passkeys)** (note that `g.co/passkeys` only leads to a marketing page). Google creates passkeys on its own too (Android, iCloud Keychain, Chrome profile), so you probably have one already and don't need to do anything. If not, create one **right now, before anything else**. It takes half a minute.

The one case you can't fix on the spot: if your account has no other passkey to approve the new one, Google may hold it as untrusted for up to a week. In that case finish the rest of the setup and run `auth` once it clears, or go straight to a service account.

A passkey isn't biometrics. Without a fingerprint reader you confirm it with your phone via a QR code, your computer password, a Windows Hello PIN or a password manager (Bitwarden, 1Password). If you'd rather skip all this, use a **service account** (below); it's exempt from the requirement.

### 1) Manager account + access level (Cloud project)

1. You need a **manager (MCC) account**. If you don't have one, create one for free at [ads.google.com/home/tools/manager-accounts](https://ads.google.com/home/tools/manager-accounts) (with an email that doesn't have a Google Ads account yet) and link your ad accounts under it.
2. Create a Google Cloud project (or use an existing one) and **enable the Google Ads API** in it: [console.cloud.google.com/apis/library/googleads.googleapis.com](https://console.cloud.google.com/apis/library/googleads.googleapis.com) → **Enable**. That gives the project *Test* access (test accounts only).
3. Apply for a higher level on the **Google Ads API Overview** page: [console.cloud.google.com/google/ads-apis/overview](https://console.cloud.google.com/google/ads-apis/overview) (pick your project). You need the Owner, Editor, Quota Administrator or Service Usage Admin role on the project. The old *Tools → API Center* in Google Ads no longer issues anything.

   | Level | Which accounts | Daily operation limit | How to get it |
   |---|---|---|---|
   | Test (automatic after enabling the API) | [test accounts](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts) only | 15,000 | a production account returns `CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION` |
   | **Explorer** | test and **production** | 2,880 / day on production | apply on the Overview page, review is usually automated. **Keyword Planner is blocked** (`keywords-research` won't run), everything else in this CLI works. Set `GOOGLE_ADS_DAILY_OP_CAP=2880`. |
   | **Basic** | test and production | **15,000 / day** | from Explorer: Overview → *Upgrade access level* → *Apply for access*. **[Brand verification](https://developers.google.com/google-ads/api/docs/api-policy/brand-verification) of the Cloud project is required** first; after that the review takes minutes. Everything incl. Keyword Planner. |
   | Standard | test and production | unlimited | for large tools |

   The limit is measured **over a sliding window of the last 24 h** (not a calendar day). The CLI tracks it locally and stops before you go over (`GOOGLE_ADS_DAILY_OP_CAP` in `.env`). Known Google issue: brand verification gets rejected for projects on a free trial or with suspended billing.

### 2) OAuth client (Cloud Console)

OAuth settings in Cloud Console have moved under **Google Auth Platform**. Older guides (including versions of this README up to 2.2.0) point to "APIs & Services → OAuth consent screen", which no longer exists. Current paths, checked on 2026-08-28:

1. Use the **same Cloud project** as in step 1 (the one with the access level and the Google Ads API enabled).
2. **Branding**: [console.cloud.google.com/auth/branding](https://console.cloud.google.com/auth/branding), the app name (you'll see it on the sign-in screen), support email, developer contact.
3. **Audience**: [console.cloud.google.com/auth/audience](https://console.cloud.google.com/auth/audience), User type **External**, and set Publishing status to **In production** via **Publish app**. In "Testing" mode Google **invalidates refresh tokens after 7 days** and you'd have to rerun `auth` every week.
4. **Clients**: [console.cloud.google.com/auth/clients](https://console.cloud.google.com/auth/clients) → **+ Create client** → Application type **Desktop app** → both values pop up once it's created.
5. → `GOOGLE_ADS_CLIENT_ID` + `GOOGLE_ADS_CLIENT_SECRET`

You don't need to add scopes by hand. The app stays "unverified" (at sign-in Google shows *Google hasn't verified this app* → *Advanced → Go to …*). For your own tool that's fine; you don't have to go through verification.

### 3) Refresh token

```bash
./run.sh auth    # opens the browser → sign in with an account that has MCC access → the token is WRITTEN into .env
```

The token is never printed (the original `.env` is backed up to `.env.bak`, both `chmod 600`). Want to print it and store it yourself? `./run.sh auth --print`. For a named profile, `./run.sh --account clientb auth` writes `GOOGLE_ADS_REFRESH_TOKEN_CLIENTB`.

> If the CLI reports `invalid_grant`: the token expired (consent screen in "Testing") or was revoked → run `./run.sh auth` again.

### 4) MCC login customer ID

Your manager account's ID **without dashes** → `GOOGLE_ADS_LOGIN_CUSTOMER_ID`. The target client account (customer ID) is then a positional argument of the commands.

### Alternative: service account (for automations, no browser)

The Google Ads API can authenticate a **service account directly**, without Workspace and without domain-wide delegation:

1. Cloud Console → **IAM & Admin → Service Accounts → Create** → create a key (**JSON**) and store it outside the repo or in the gitignored `.secrets/` folder.
2. In Google Ads (the MCC or the account itself) → **Admin → Access and security → Users → +** → enter the service account's email and give it a role (Standard is enough for managing campaigns).
3. In `.env`: `GOOGLE_ADS_JSON_KEY_FILE_PATH=.secrets/service-account.json` (+ `GOOGLE_ADS_DEVELOPER_TOKEN` and `GOOGLE_ADS_LOGIN_CUSTOMER_ID`). `CLIENT_ID/SECRET/REFRESH_TOKEN` are then not needed. Optionally `GOOGLE_ADS_IMPERSONATED_EMAIL` for Workspace delegation.

Upsides: nothing expires, access doesn't hang on your personal login, and it suits crons and agents. The key is a password; never commit it.

> Every value in `.env` is a password to your ad accounts. It goes **into `.env` only** (it's in `.gitignore`), never into code, git or a chat.

### Test account (optional sandbox)

Want to try the API without risk? Create a [test manager account](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts) (with a different Google account than your production MCC), a test client account under it, and call it with the **same Cloud project and OAuth client** (Test access is enough there). Test accounts don't serve or bill anything; Google deletes them after a year of inactivity.

### Multi-account

You can duplicate any variable in `.env` with a `_<NAME>` suffix (uppercase) → pick the profile with the global `--account <name>` switch:

```bash
GOOGLE_ADS_REFRESH_TOKEN_CLIENTB=...
GOOGLE_ADS_LOGIN_CUSTOMER_ID_CLIENTB=...
```
```bash
./run.sh --account clientb accounts
```

The **target account's customer ID** is a positional argument of most commands (with or without dashes, the CLI strips them). List of accounts under the MCC (full hierarchy): `./run.sh accounts`.

## Usage

```bash
./run.sh <command> [flags]
# equivalent: source .venv/bin/activate && python google_ads_cli.py <command> [flags]
```

**Conventions across the CLI:**

- **Money in the account currency** (e.g. CZK). The CLI converts to and from micros (×1,000,000) itself.
- **`--json`**: machine-readable output (use it when parsing; works before or after the command name).
- **Every mutation is a dry-run by default**: it prints the plan and checks feasibility through the API's `validate_only`, but **writes nothing**. The real write happens only with `--confirm`.
- **REMOVED is permanent** (Google Ads has no undelete). Deleting therefore requires the entity to be PAUSED (`--force` overrides). You can change your mind about a pause; a deletion can't be undone.
- Listings hide REMOVED entities by default (they stay visible in the API forever) and **never truncate data**: `search_stream` returns everything; where `--limit` shortens the output, the CLI says so.
- Dates in `YYYY-MM-DD` format; measure performance over 60–90 day windows (conversion lag).

### Account protection (quotas and rate limits)

- **Daily quota**: Basic Access = 15,000 operations (Explorer 2,880) **over a sliding 24 h window** per Cloud project access level (a read request = 1 op regardless of rows; mutation = 1 op per operation; validate_only dry-runs are counted too, because Google doesn't document an exemption, so the local estimate is always ≥ reality). The CLI tracks usage locally in `.quota/` per account and **stops BEFORE you go over** (`GOOGLE_ADS_DAILY_OP_CAP` in `.env`; Standard Access has no limit, so set it high).
- **QPS limits** (token bucket per account + token): on `RESOURCE_EXHAUSTED` the CLI waits 5→10→20 s (honouring the pause Google recommends), max 3 attempts, then gives up. It never hammers the API in a loop. Transient outages (UNAVAILABLE) are retried for **reads** only; a write may have landed, so it is never repeated. Keyword Planner is limited to 1 request/s, so run research sequentially.
- Status: `./run.sh quota`, limits + usage: `./run.sh api-limits`.

## Commands

### Setup & account

| Command | Description |
|--------|-------|
| `auth [--print]` | One-off OAuth flow → **writes** the refresh token **into `.env`** (`--print` prints it instead) |
| `accounts` | Full account hierarchy under the MCC (ID, name, currency, time zone, level) |
| `quota` | Local operation usage over the last 24 h vs. the cap |
| `api-limits` | Documented API limits (version, access levels, windows) + live local usage |

### Overview & reporting

| Command | Description |
|--------|-------|
| `pulse <cid> [--days N] [--no-compare]` | **Account overview in 5 operations**: totals, per campaign, deltas vs. the previous window, top movers, optimization score, number of recommendations, policy problems + warnings (broken measurement, capped budgets). Default window is 7 days ending yesterday |
| `query <cid> --gaql "…"` | Any GAQL query (the core of reporting) |
| `report <cid> --entity campaign\|ad_group\|keyword --from --to` | Preset performance report |
| `changes <cid> [--days N] [--sweep] [--limit N]` | Who changed what (≤30 days, old→new, author); `--sweep` = cheap overview of what moved (≤90 days). The API requires a LIMIT here (default 200, max 10,000); when the result hits it, the CLI warns |

> **Run `pulse` first** whenever you look at an account. It replaces chaining campaigns+report+query and returns a compact digest. Dig into detail only where pulse points.

### Research

| Command | Description |
|--------|-------|
| `keywords-research <cid> --seed "kw1,kw2" [--language] [--geo] [--limit]` | Keyword Planner: search volume, competition, CPC (1 request/s!). **Requires Basic Access**; on the Explorer level KeywordPlanIdeaService is blocked |
| `search-terms <cid> --from --to` | Actual search queries (source of negatives) |

### Campaigns

| Command | Description |
|--------|-------|
| `campaigns <cid> [--status]` | List search campaigns |
| `campaign-create <cid> --name --budget [--bidding] [--target-cpa] [--target-roas] [--geo] [--language] [--no-search-partners] [--presence-only]` | New SEARCH campaign + budget + geo/language atomically, **starts PAUSED** (default targeting: Czech Republic + Czech; search partners on and "presence or interest" unless you switch them off) |
| `campaign-status <cid> <id> --status enabled\|paused\|removed [--force]` | Enable / pause / delete (delete only from PAUSED!) |
| `bidding-set <cid> <id> --strategy … [--target-cpa] [--target-roas]` | Bidding: `manual_cpc`, `max_conversions`, `max_conversion_value`, `target_cpa`, `target_roas` |
| `bidding-set <cid> <id> --portfolio <bidding_strategy_id>` | Attach the campaign to an existing portfolio bidding strategy (the target is set on the portfolio) |
| `campaign-targeting <cid> <id>` | Campaign targeting criteria (geo/language/schedule/device/proximity) |

### Budgets

| Command | Description |
|--------|-------|
| `budgets <cid>` | Budgets incl. shared ones and Google's recommended amounts |
| `budget-set <cid> <campaign_id> --amount <amount>` | Campaign daily budget (warns if shared) |
| `budget-create <cid> --name --amount` | New **shared** budget |
| `budget-assign <cid> --budget-id --campaigns "id1,id2"` | Move campaigns onto a (shared) budget |
| `budget-remove <cid> --budget-id` | Delete an orphaned budget (no campaigns attached) |

### Ad groups & ads

| Command | Description |
|--------|-------|
| `ad-groups <cid> [--campaign]` | List ad groups |
| `ad-group-create <cid> --campaign --name [--cpc]` | New ad group |
| `ads <cid> [--ad-group] [--campaign]` | RSA ads: status, **Ad Strength**, approval status |
| `rsa-create <cid> --ad-group --headlines "a\|b\|c" --descriptions "x\|y" --final-url [--path1] [--path2]` | New RSA (3–15 headlines ≤30, 2–4 descriptions ≤90). A **preflight lint** checks limits and style violations before calling the API. Pinning: ` @H1`/`@H2`/`@H3`/`@D1`/`@D2` at the end of the text |
| `ad-status <cid> <ad_group_id> <ad_id> --status … [--force]` | Enable / pause / delete an ad (delete only from PAUSED) |
| `ad-update-url <cid> <ad_id> --final-url` | Change the Final URL in place (keeps history; the only editable field, texts are immutable) |
| `ad-policy <cid> [--only-problems] [--campaign] [--ad-group]` | **Approval check**: approval/review status + policy topics (Google approves asynchronously, ≤1 business day) |

> **Changing ad text**: texts are immutable in the API → `rsa-create` a new one + pause and delete the old one (`ad-status`). A status update to REMOVED would silently do nothing, so the CLI uses a remove operation.

### Keywords & negatives

| Command | Description |
|--------|-------|
| `keywords <cid> [--ad-group] [--campaign]` | List keywords with criterion IDs (for remove) |
| `keyword-add <cid> --ad-group --keywords-json '[{"text":"…","match_type":"phrase","cpc":25}]'` | Batch-add keywords (`exact`/`phrase`/`broad`) |
| `keyword-remove <cid> --criteria "agId~critId,…"` | Remove keyword criteria |
| `negative-add <cid> --ad-group\|--campaign --keywords "a,b" [--match-type]` | Negatives on an ad group/campaign |

### Shared sets (shared negative lists)

| Command | Description |
|--------|-------|
| `shared-sets <cid>` | Lists + where they're attached |
| `shared-set-create <cid> --name [--type negative-keywords\|account-negatives]` | New list |
| `shared-set-add <cid> --set --keywords "a,b" [--match-type]` | Fill with negatives |
| `shared-set-keywords <cid> --set` | List contents (criterion IDs) |
| `shared-set-remove-keywords <cid> --set --criteria "id1,id2"` | Remove from the list |
| `shared-set-attach <cid> --set --campaigns "id1,id2" [--detach]` | Attach to / detach from campaigns |
| `customer-negatives-attach <cid> --set` | An account-negatives list on the **whole account** (max 1,000 keywords) |
| `customer-negatives-detach <cid> --criterion` | Detach account-level negatives (attach prints the ID) |
| `shared-set-remove <cid> --set` | Delete the whole list (incl. contents) |

### Assets (sitelinks, callouts, snippets)

| Command | Description |
|--------|-------|
| `assets <cid> [--type sitelink\|callout\|snippet]` | List assets with IDs |
| `asset-links <cid>` | What's linked where (account/campaign/ad group) |
| `sitelink-create <cid> --sitelinks-json '[{"text":"…","url":"…","desc1":"…","desc2":"…"}]'` | Sitelinks (text ≤25, desc ≤35; you need ≥2 for them to show) |
| `callout-create <cid> --texts "a\|b\|c"` | Callouts (≤25 characters) |
| `snippet-create <cid> --header Courses --values "a\|b\|c"` | Structured snippet (header from a fixed list, 3–10 values ≤25) |
| `asset-link <cid> --asset "id1,id2" --field-type sitelink\|callout\|snippet --campaign\|--ad-group\|--customer` | Link assets |
| `asset-unlink <cid> --asset … --field-type … --campaign\|--ad-group\|--customer` | Unlink (the assets themselves can't be deleted; they're create-only) |

### Audiences / remarketing

| Command | Description |
|--------|-------|
| `audiences <cid>` | User lists: size for search, eligibility |
| `audience-create <cid> --name --url-contains "…" [--membership-days 30]` | Rule-based list (URL visitors; collected by the web tag) |
| `audiences-attached <cid> [--campaign]` | What's attached where (incl. exclusions) |
| `audience-attach <cid> --list --campaign\|--ad-group [--mode observation\|targeting] [--bid-modifier]` | Attach an audience. **`observation`** = measurement/bids only (the safe default for search); **`targeting` narrows serving to the audience only!** |
| `audience-exclude <cid> --list --campaign` | Exclude an audience from a campaign (e.g. customers from acquisition) |
| `audience-detach <cid> --criterion --campaign\|--ad-group` | Detach |

### Targeting

| Command | Description |
|--------|-------|
| `geo-suggest --name "Prague,Brno" [--country CZ]` | Look up geo target IDs by name |
| `geo-target <cid> <campaign_id> --geo "ids" [--negative] [--proximity "lat,lng,km"] [--remove ids]` | Geo targeting / exclusion / radius |
| `language-target <cid> <campaign_id> --language "1021" [--remove ids]` | Languages (1021=cs, 1034=sk, 1000=en; positive only) |
| `schedule-set <cid> <campaign_id> --schedule-json '[{"day":"MONDAY","start":8,"end":20,"bid_modifier":1.1}]'` | **Replaces** the whole schedule atomically (`[]` = 24/7; max 6 blocks/day) |
| `device-bid <cid> <campaign_id> --device mobile --modifier 0.8` | Device bid modifier (0 = don't show on that device) |
| `demographics <cid> [--ad-group]` | Ad group demographic criteria |
| `demographic-target <cid> --ad-group --value "AGE_RANGE_25_34,MALE" [--negative] [--modifier] [--remove ids]` | Demographics: targeting/exclusion (age/gender/income) |

> ⚠️ A campaign without geo and language criteria serves **worldwide in all languages**. That's why `campaign-create` sets targeting by default; after manual changes, verify with `campaign-targeting`.

### Conversion actions

| Command | Description |
|--------|-------|
| `conversions <cid>` | List: status, category, **primary/secondary**, counting |
| `conversion-create <cid> --name --category PURCHASE\|SUBMIT_LEAD_FORM\|… [--primary] [--counting one\|many] [--value]` | New WEBPAGE action (a tag/GTM has to measure it!) |
| `conversion-update <cid> <id> [--status] [--primary yes\|no] [--counting] [--value]` | Edit an action |

> `metrics.conversions` counts **primary** actions only (the ones Smart Bidding optimizes for); `all_conversions` counts everything. `pulse` warns automatically when primary is 0 and all isn't (usually a misconfigured action).

### Google's recommendations

| Command | Description |
|--------|-------|
| `recommendations <cid>` | List with type, impact, resource name |
| `recommendation-apply <cid> --resource "…"` | Apply (as Google proposes it; for your own values, prefer `budget-set` etc.) |
| `recommendation-dismiss <cid> --resource "…"` | Dismiss (stops dragging down the optimization score) |

> Recommendation resource names regenerate (daily or more often), so list and apply/dismiss in the same session.

### Labels

| Command | Description |
|--------|-------|
| `labels <cid>` / `label-create <cid> --name [--description] [--color]` | List / create |
| `label-assign` / `label-unassign <cid> --label <id> --campaign\|--ad-group\|--ad "agId~adId"\|--keyword "agId~critId"` | Assign / remove |
| `label-remove <cid> --label <id>` | Delete a label (incl. all assignments) |

### DSA (Dynamic Search Ads)

| Command | Description |
|--------|-------|
| `dsa-setting <cid> <campaign_id> --domain example.com [--language-code en]` | Campaign DSA settings |
| `dsa-ad-group-create <cid> --campaign --name [--cpc]` | DSA ad group (no keywords and no RSA!) |
| `dsa-create <cid> --ad-group --descriptions "a\|b"` | DSA ad (Google generates the headline + URL) |
| `webpage-targets <cid> --ad-group` | Ad group webpage criteria |
| `webpage-target-add <cid> --ad-group --name --conditions "url:blog,title:course" [--negative] [--cpc]` | Page targeting (≤3 AND conditions; no conditions = the whole site) |
| `webpage-target-remove <cid> --criteria "agId~critId"` | Remove |

### Performance Max (reporting only)

| Command | Description |
|--------|-------|
| `pmax <cid> --from --to [--channels]` | PMax campaign metrics (`--channels` = breakdown by network) |
| `pmax-search-terms <cid> --from --to [--campaign] [--limit N]` | PMax search terms (everything; `--limit` only trims the output and says so) |

### Experiments

| Command | Description |
|--------|-------|
| `experiments <cid>` | List experiments |
| `experiment-create <cid> --campaign --name --start --end [--traffic-split 50]` | SEARCH_CUSTOM experiment + arms; generates a **draft campaign** to edit |
| `experiment-schedule <cid> <id>` | Launch (async; schedule the start in the future to leave time for ad review) |
| `experiment-results <cid> <id>` | Results: treatment vs. control |
| `experiment-end <cid> <id>` | End without applying changes |
| `experiment-promote <cid> <id>` | Apply the treatment changes to the base campaign |

## Examples

```bash
# Account overview for the last 7 days (vs. the previous 7) — the first step of any analysis
./run.sh pulse 123-456-7890

# Keyword research (Basic Access; 1 request/s)
./run.sh keywords-research 1234567890 --seed "ai course,ai training" --limit 50

# Build a campaign top-down — every step is a dry-run first, then --confirm
./run.sh campaign-create 1234567890 --name "AI courses – Search" --budget 500 --bidding max_conversions
./run.sh campaign-create 1234567890 --name "AI courses – Search" --budget 500 --bidding max_conversions --confirm
./run.sh ad-group-create 1234567890 --campaign 111 --name "AI course" --cpc 20 --confirm
./run.sh keyword-add 1234567890 --ad-group 222 \
  --keywords-json '[{"text":"ai course","match_type":"phrase","cpc":25},{"text":"ai training","match_type":"exact"}]' --confirm
./run.sh rsa-create 1234567890 --ad-group 222 \
  --headlines "AI First @H1|AI Course for Marketers|Start Today|Practical AI at Work" \
  --descriptions "Learn to use AI in your everyday work.|A video course that saves hours of work." \
  --final-url "https://example.com" --confirm
./run.sh negative-add 1234567890 --campaign 111 --keywords "free,jobs,salary" --confirm
./run.sh campaign-targeting 1234567890 111        # check geo + language before enabling
./run.sh ad-policy 1234567890 --only-problems     # after the ads are reviewed

# Turn the campaign off on tablets, limit the schedule
./run.sh device-bid 1234567890 111 --device tablet --modifier 0 --confirm
./run.sh schedule-set 1234567890 111 --schedule-json '[{"day":"MONDAY","start":8,"end":20}]' --confirm

# Reporting for further processing
./run.sh report 1234567890 --entity keyword --from 2026-06-01 --to 2026-08-20 --json
./run.sh search-terms 1234567890 --from 2026-06-01 --to 2026-08-20 --json
```

## Claude Code skill (`/google-ads`)

`skill/google-ads/` contains a bundled skill that turns the app into a "Google Ads agent": scenarios (research → create → optimize → policy-check → negatives → audiences), safety rules (plan → approval → `--confirm`, PAUSED start, quotas) and ad-writing rules. Installation: **[skill/INSTALL.md](skill/INSTALL.md)** (copy into `~/.claude/skills/` + set the path). The install guide is in Czech.

The skill gives you the **mechanics** (how to do things with the tool) and the **rules** (what Google allows). The ongoing optimization strategy is yours to set to fit your goals.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

The suite runs **fully offline, with no credentials**: every write command builds its operations against the real API v25 proto types (a typo in a field/enum name = a red test), and a recorder replaces the gRPC calls. It covers the dry-run default, the PAUSED-before-REMOVED brake, the sliding quota, the retry policy, presence-aware update masks, the lint, writing the token into `.env`, and first contact through the CLI (`--help`, `--json`, error paths without tracebacks).

## Project structure

```
google-ads-app/
├── google_ads_cli.py   # Thin entrypoint (calls gads.cli.main)
├── gads/               # Implementation package
│   ├── api.py          #   engine: .env + accounts, client (API version pin), quota guard, retry, query/mutation runners
│   ├── formatting.py   #   micros⇄currency, JSON output, errors
│   ├── lint.py         #   preflight text lint (RSA/assets)
│   ├── cli.py          #   argparse + dispatch (_cmd = parser + handler in one)
│   └── commands/       #   one module per domain (campaigns, ads, keywords, …)
├── tests/              # Offline pytest suite (117 tests)
├── scripts/check_docs_consistency.py   # CLI ↔ README ↔ CLAUDE.md ↔ skill
├── requirements.txt · requirements-dev.txt
├── setup.sh · run.sh   # Install / run scripts (activates the venv)
├── .env.example        # Credentials template
├── CLAUDE.md           # Signpost for Claude Code (+ documentation map)
├── docs/api-notes.md   # Dense reference of Google Ads API behaviour
├── CHANGELOG.md        # Version history
├── .env                # Credentials (DO NOT COMMIT)
└── skill/              # Claude Code skill (/google-ads) + INSTALL.md
```

## Documentation

- **[docs/api-notes.md](docs/api-notes.md)**: how the Google Ads API behaves in practice (versions, access levels, quotas, immutability, quirks, composite resource names)
- **[CHANGELOG.md](CHANGELOG.md)**: version history (subscribe via Watch → Custom → Releases)
- **[CLAUDE.md](CLAUDE.md)**: code orientation for coding agents

## Bugs and ideas

Something broken or missing? Open a **GitHub Issue**. Pull requests are welcome. The repo is primarily educational, so follow the style of the surrounding code and include a test.

## License

[MIT](LICENSE) © 2026 Jindřich Fáborský

## Author

[Jindřich Fáborský](https://www.faborsky.com), marketer and educator from Prague. I teach marketers to build their own tools with AI.

Google Ads App started as teaching material for my course on vibe coding in marketing, as an example of a tool you build for your everyday campaign work that then saves you hours of routine.
