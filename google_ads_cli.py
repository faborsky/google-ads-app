#!/usr/bin/env python3
"""Google Ads CLI — read-only foundation (Phase 1).

Mirrors the Sklik tooling pattern: a mechanical CLI driven by a strategic skill.
This phase is READ-ONLY (reporting + research). Write/mutate commands come later.

Auth model (OAuth2, configured via .env):
  developer_token + client_id + client_secret + refresh_token + login_customer_id

Quota & rate limits (so the app never gets the account throttled/blocked):
  - Daily operation quota: Basic Access = 15000 ops/day (reads + mutates
    combined); Standard Access = effectively unlimited. A Search/SearchStream
    request counts as 1 operation regardless of rows returned; each mutate op
    counts as 1. We track ops locally per account/Pacific-day in .quota/ and
    HARD-STOP before a call would exceed the cap (raise GOOGLE_ADS_DAILY_OP_CAP
    for Standard Access).
  - Per-second rate limits (QPS, metered per CID + developer token): the server
    returns RESOURCE_EXHAUSTED / RESOURCE_TEMPORARILY_EXHAUSTED. We retry those
    with exponential back-off (honouring Google's suggested retry delay).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_VERSION = "v24"
QUOTA_DIR = BASE_DIR / ".quota"
SCOPES = ["https://www.googleapis.com/auth/adwords"]

# Google Ads daily quota resets at midnight Pacific time, so the local op
# counter is bucketed by the Pacific date (not the machine's local date).
GOOGLE_TZ = ZoneInfo("America/Los_Angeles")


def _today() -> str:
    """Current date in Google's quota timezone (Pacific), ISO format."""
    return _dt.datetime.now(GOOGLE_TZ).date().isoformat()

# Sensible defaults for Jindřich's Czech accounts (AI First / HYW / Marketing Festival)
DEFAULT_LANGUAGE_ID = "1021"      # Czech
DEFAULT_GEO_TARGET_ID = "2203"    # Czech Republic


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _die(msg: str, code: int = 1) -> None:
    _err(f"Error: {msg}")
    sys.exit(code)


def _output_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _micros(m) -> float:
    """Convert API micros to currency units."""
    return (m or 0) / 1_000_000


def _fmt_money(m, currency: str = "") -> str:
    return f"{_micros(m):,.2f} {currency}".strip()


def _to_micros(units) -> int:
    """Convert currency units to API micros."""
    return int(round(float(units) * 1_000_000))


# ---------------------------------------------------------------------------
# Account / credential resolution (multi-account via env suffixes)
# ---------------------------------------------------------------------------
def _env(key: str, account: str | None) -> str | None:
    """Resolve an env var, preferring the named-account variant when present."""
    if account and account != "default":
        v = os.getenv(f"{key}_{account.upper()}")
        if v:
            return v
    return os.getenv(key)


def _config_dict(account: str | None) -> dict:
    cfg = {
        "developer_token": _env("GOOGLE_ADS_DEVELOPER_TOKEN", account),
        "client_id": _env("GOOGLE_ADS_CLIENT_ID", account),
        "client_secret": _env("GOOGLE_ADS_CLIENT_SECRET", account),
        "refresh_token": _env("GOOGLE_ADS_REFRESH_TOKEN", account),
        "login_customer_id": _env("GOOGLE_ADS_LOGIN_CUSTOMER_ID", account),
        "use_proto_plus": True,
    }
    missing = [k for k in ("developer_token", "client_id", "client_secret", "refresh_token") if not cfg[k]]
    if missing:
        _die(
            "Missing credentials in .env: "
            + ", ".join(f"GOOGLE_ADS_{m.upper()}" for m in missing)
            + (f" (account: {account})" if account and account != "default" else "")
            + ".\n  Run ./run.sh auth to generate a refresh token, and fill in the rest."
        )
    # login_customer_id must be digits only (no dashes)
    if cfg["login_customer_id"]:
        cfg["login_customer_id"] = cfg["login_customer_id"].replace("-", "")
    return cfg


def _get_client(account: str | None):
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        _die("google-ads not installed. Run ./setup.sh first.")
    return GoogleAdsClient.load_from_dict(_config_dict(account), version=API_VERSION)


def _clean_id(cid: str) -> str:
    return cid.replace("-", "").strip()


# ---------------------------------------------------------------------------
# Quota tracking — Basic Access = 15000 ops/day. Tracked locally per account/day.
# Reads are counted by returned rows (a conservative proxy); mutations = 1/op.
# ---------------------------------------------------------------------------
def _quota_file(account: str | None) -> Path:
    today = _today()
    name = (account or "default").lower()
    return QUOTA_DIR / f"{name}_{today}.json"


def _quota_cap() -> int:
    try:
        return int(os.getenv("GOOGLE_ADS_DAILY_OP_CAP", "15000"))
    except ValueError:
        return 15000


def _quota_read(account: str | None) -> int:
    f = _quota_file(account)
    if f.exists():
        try:
            return int(json.loads(f.read_text()).get("ops", 0))
        except (ValueError, json.JSONDecodeError):
            return 0
    return 0


def _track_ops(account: str | None, n: int) -> None:
    if n <= 0:
        return
    QUOTA_DIR.mkdir(exist_ok=True)
    f = _quota_file(account)
    used = _quota_read(account) + n
    f.write_text(json.dumps({"ops": used, "date": _today()}))
    cap = _quota_cap()
    if used >= cap:
        _err(f"⚠️  QUOTA: {used}/{cap} operations used today — daily cap reached.")
    elif used >= cap * 0.8:
        _err(f"⚠️  QUOTA: {used}/{cap} operations used today ({used / cap:.0%}).")


def _quota_guard(account: str | None, n: int) -> None:
    """Refuse BEFORE a call that would exceed the daily operation cap.

    Basic Access = 15000 ops/day. Standard Access has no daily op limit — raise
    GOOGLE_ADS_DAILY_OP_CAP (or set it very high) so this never blocks you.
    """
    if n <= 0:
        return
    cap = _quota_cap()
    used = _quota_read(account)
    if used + n > cap:
        _die(f"QUOTA: {used}/{cap} operací dnes — dalších {n} by překročilo denní "
             f"limit účtu '{(account or 'default')}'. Počkej na reset (půlnoc Pacific) "
             f"nebo, pokud máš Standard Access (bez denního limitu), zvyš "
             f"GOOGLE_ADS_DAILY_OP_CAP v .env.")


def _rate_error_retry_after(ex) -> int | None:
    """If the exception is a quota/rate-exhaustion error, return a retry delay in
    seconds (Google's suggested delay when present, else 0 = use our back-off);
    otherwise None (not a rate error → not retryable)."""
    try:
        for err in ex.failure.errors:
            if err.error_code.quota_error:  # RESOURCE_EXHAUSTED / _TEMPORARILY_
                qd = getattr(getattr(err, "details", None), "quota_error_details", None)
                secs = getattr(getattr(qd, "retry_delay", None), "seconds", 0)
                return int(secs) if secs else 0
    except (AttributeError, ValueError):
        pass
    return None


def _execute_with_retry(call, what: str):
    """Run an API call, retrying on quota/rate exhaustion with exponential
    back-off (honouring Google's suggested delay). Non-rate errors are reported
    and abort, exactly as before."""
    from google.ads.googleads.errors import GoogleAdsException

    backoff = 5
    for attempt in range(4):  # initial try + up to 3 retries
        try:
            return call()
        except GoogleAdsException as ex:
            retry_after = _rate_error_retry_after(ex)
            if retry_after is None:
                _report_google_ads_exception(ex)  # not a rate error → dies
                return None
            if attempt == 3:
                _die(f"Rate limit ({what}) přetrvává i po 3 pokusech — končím, ať "
                     f"účet nezatěžuju dál. Zkus to za chvíli.")
            wait = retry_after or backoff
            _err(f"⏳ Rate limit ({what}) — čekám {wait}s a zkouším znovu "
                 f"(pokus {attempt + 1}/3)…")
            time.sleep(wait)
            backoff *= 2
    return None


# ---------------------------------------------------------------------------
# Query execution — returns rows, tracks quota by row count.
# ---------------------------------------------------------------------------
def _run_query(client, customer_id: str, gaql: str, account: str | None) -> list:
    service = client.get_service("GoogleAdsService")

    # A Search/SearchStream request = 1 operation regardless of rows returned.
    _quota_guard(account, 1)

    def _call() -> list:
        rows: list = []
        stream = service.search_stream(request={"customer_id": customer_id, "query": gaql})
        for batch in stream:
            rows.extend(batch.results)
        return rows

    rows = _execute_with_retry(_call, what=f"query {customer_id}") or []
    _track_ops(account, 1)  # 1 op per request — NOT per row
    return rows


def _report_google_ads_exception(ex) -> None:
    msgs = []
    for error in ex.failure.errors:
        loc = ""
        if error.location and error.location.field_path_elements:
            loc = " on " + ".".join(e.field_name for e in error.location.field_path_elements)
        msgs.append(f"  - {error.message}{loc}")
    _die("Google Ads API request failed (request_id="
         + f"{ex.request_id}):\n" + "\n".join(msgs))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_auth(args: argparse.Namespace) -> None:
    """One-time OAuth2 flow → generates a refresh token to paste into .env."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        _die("google-auth-oauthlib not installed. Run ./setup.sh first.")

    client_id = _env("GOOGLE_ADS_CLIENT_ID", args.account)
    client_secret = _env("GOOGLE_ADS_CLIENT_SECRET", args.account)
    if not client_id or not client_secret:
        _die("Set GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET in .env before running auth.")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    print("Opening your browser to authorize access to Google Ads…")
    print("Sign in as faborsky@gmail.com and grant access.\n")
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        _die("No refresh token returned. Make sure the OAuth consent screen has you as a Test user.")

    suffix = "" if not args.account or args.account == "default" else f"_{args.account.upper()}"
    print("\n✅ Success! Add this line to your .env:\n")
    print(f"GOOGLE_ADS_REFRESH_TOKEN{suffix}={creds.refresh_token}\n")
    if args.json:
        _output_json({"refresh_token": creds.refresh_token})


def cmd_accounts(args: argparse.Namespace) -> None:
    """List accounts accessible to the authenticated user (under the MCC)."""
    client = _get_client(args.account)
    customer_service = client.get_service("CustomerService")
    try:
        resource_names = customer_service.list_accessible_customers().resource_names
    except Exception as ex:  # noqa: BLE001 — surface auth/setup errors clearly
        _die(str(ex))
    _track_ops(args.account, 1)  # listAccessibleCustomers = 1 op

    seed = _env("GOOGLE_ADS_LOGIN_CUSTOMER_ID", args.account)
    accounts = []
    if seed:
        # Expand the MCC hierarchy for human-friendly names/currency/timezone.
        gaql = """
            SELECT customer_client.id, customer_client.descriptive_name,
                   customer_client.currency_code, customer_client.time_zone,
                   customer_client.manager, customer_client.level, customer_client.status
            FROM customer_client
            WHERE customer_client.level <= 1
        """
        for row in _run_query(client, _clean_id(seed), gaql, args.account):
            cc = row.customer_client
            accounts.append({
                "id": str(cc.id),
                "name": cc.descriptive_name,
                "currency": cc.currency_code,
                "time_zone": cc.time_zone,
                "manager": cc.manager,
                "level": cc.level,
                "status": cc.status.name if hasattr(cc.status, "name") else str(cc.status),
            })
    else:
        accounts = [{"resource_name": rn} for rn in resource_names]

    if args.json:
        _output_json(accounts)
        return
    if not accounts:
        print("No accounts found.")
        return
    for a in accounts:
        if "name" in a:
            tag = " [MCC]" if a.get("manager") else ""
            print(f"{a['id']:>12}  {a['name']}{tag}  ({a['currency']}, {a['time_zone']}, {a['status']})")
        else:
            print(a["resource_name"])


def cmd_campaigns(args: argparse.Namespace) -> None:
    """List search campaigns for a customer."""
    client = _get_client(args.account)
    where = "WHERE campaign.advertising_channel_type = 'SEARCH'"
    if args.status:
        where += f" AND campaign.status = '{args.status.upper()}'"
    gaql = f"""
        SELECT campaign.id, campaign.name, campaign.status,
               campaign.advertising_channel_type, campaign.bidding_strategy_type,
               campaign_budget.amount_micros
        FROM campaign
        {where}
        ORDER BY campaign.name
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = [{
        "id": str(r.campaign.id),
        "name": r.campaign.name,
        "status": r.campaign.status.name,
        "bidding_strategy": r.campaign.bidding_strategy_type.name,
        "daily_budget": _micros(r.campaign_budget.amount_micros),
    } for r in rows]

    if args.json:
        _output_json(out)
        return
    if not out:
        print("No search campaigns found.")
        return
    for c in out:
        print(f"{c['id']:>12}  {c['status']:<8}  budget {c['daily_budget']:>10,.0f}  "
              f"{c['bidding_strategy']:<22}  {c['name']}")


def cmd_query(args: argparse.Namespace) -> None:
    """Run an arbitrary GAQL query (the reporting core)."""
    client = _get_client(args.account)
    rows = _run_query(client, _clean_id(args.customer_id), args.gaql, args.account)
    if args.json:
        from google.protobuf.json_format import MessageToDict
        _output_json([MessageToDict(r._pb) for r in rows])
    else:
        from google.protobuf.json_format import MessageToDict
        for r in rows:
            print(json.dumps(MessageToDict(r._pb), ensure_ascii=False))
    _err(f"({len(rows)} rows)")


# Reporting presets: entity -> (FROM clause, selected fields)
_REPORT_PRESETS = {
    "campaign": ("campaign", [
        "campaign.id", "campaign.name", "campaign.status",
    ]),
    "ad_group": ("ad_group", [
        "ad_group.id", "ad_group.name", "campaign.name",
    ]),
    "keyword": ("keyword_view", [
        "ad_group_criterion.criterion_id", "ad_group_criterion.keyword.text",
        "ad_group_criterion.keyword.match_type", "ad_group.name", "campaign.name",
    ]),
}
_REPORT_METRICS = [
    "metrics.impressions", "metrics.clicks", "metrics.ctr",
    "metrics.average_cpc", "metrics.cost_micros",
    "metrics.conversions", "metrics.conversions_value",
]


def cmd_report(args: argparse.Namespace) -> None:
    """Preset performance report for campaign / ad_group / keyword over a date range."""
    if args.entity not in _REPORT_PRESETS:
        _die(f"Unknown entity '{args.entity}'. Choose: {', '.join(_REPORT_PRESETS)}")
    from_table, fields = _REPORT_PRESETS[args.entity]
    select = ", ".join(fields + _REPORT_METRICS)
    gaql = f"""
        SELECT {select}
        FROM {from_table}
        WHERE segments.date BETWEEN '{args.date_from}' AND '{args.date_to}'
        ORDER BY metrics.cost_micros DESC
    """
    client = _get_client(args.account)
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)

    from google.protobuf.json_format import MessageToDict
    out = [MessageToDict(r._pb) for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("No data for the given range.")
        return
    for r in out:
        m = r.get("metrics", {})
        label = (r.get("campaign", {}).get("name")
                 or r.get("adGroup", {}).get("name")
                 or r.get("adGroupCriterion", {}).get("keyword", {}).get("text", "?"))
        print(f"{label[:40]:<40}  impr {int(m.get('impressions', 0)):>8}  "
              f"clicks {int(m.get('clicks', 0)):>6}  "
              f"cost {_micros(int(m.get('costMicros', 0))):>10,.0f}  "
              f"conv {float(m.get('conversions', 0)):>7.1f}")


def cmd_keywords_research(args: argparse.Namespace) -> None:
    """Keyword Planner — generate keyword ideas with volume / competition / CPC."""
    client = _get_client(args.account)
    svc = client.get_service("KeywordPlanIdeaService")
    gtc_service = client.get_service("GoogleAdsService")

    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = _clean_id(args.customer_id)
    request.language = gtc_service.language_constant_path(args.language)
    request.geo_target_constants.append(
        gtc_service.geo_target_constant_path(args.geo)
    )
    request.keyword_plan_network = (
        client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    )
    seeds = [s.strip() for s in args.seed.split(",") if s.strip()]
    request.keyword_seed.keywords.extend(seeds)

    # GenerateKeywordIdeas is a non-Get/Mutate/Search call = 1 operation.
    _quota_guard(args.account, 1)
    response = _execute_with_retry(
        lambda: svc.generate_keyword_ideas(request=request),
        what=f"keyword-ideas {request.customer_id}",
    )
    if response is None:
        return

    ideas = []
    for idea in response:
        m = idea.keyword_idea_metrics
        ideas.append({
            "keyword": idea.text,
            "avg_monthly_searches": m.avg_monthly_searches,
            "competition": m.competition.name if hasattr(m.competition, "name") else str(m.competition),
            "low_top_of_page_bid": _micros(m.low_top_of_page_bid_micros),
            "high_top_of_page_bid": _micros(m.high_top_of_page_bid_micros),
        })
    _track_ops(args.account, 1)  # 1 op per generate request, not per idea
    ideas.sort(key=lambda k: k["avg_monthly_searches"], reverse=True)
    if args.limit:
        ideas = ideas[: args.limit]

    if args.json:
        _output_json(ideas)
        return
    if not ideas:
        print("No keyword ideas returned.")
        return
    print(f"{'keyword':<40}  {'searches/mo':>11}  {'comp':<8}  {'CPC low–high'}")
    for k in ideas:
        print(f"{k['keyword'][:40]:<40}  {k['avg_monthly_searches']:>11,}  "
              f"{k['competition']:<8}  {k['low_top_of_page_bid']:.2f}–{k['high_top_of_page_bid']:.2f}")


def cmd_search_terms(args: argparse.Namespace) -> None:
    """Actual search queries that triggered ads — the source for negative keywords."""
    client = _get_client(args.account)
    gaql = f"""
        SELECT search_term_view.search_term, segments.search_term_match_type,
               campaign.name, ad_group.name,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{args.date_from}' AND '{args.date_to}'
        ORDER BY metrics.cost_micros DESC
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    from google.protobuf.json_format import MessageToDict
    out = [MessageToDict(r._pb) for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("No search terms for the given range.")
        return
    for r in out:
        m = r.get("metrics", {})
        term = r.get("searchTermView", {}).get("searchTerm", "?")
        print(f"{term[:45]:<45}  impr {int(m.get('impressions', 0)):>7}  "
              f"clicks {int(m.get('clicks', 0)):>5}  "
              f"cost {_micros(int(m.get('costMicros', 0))):>9,.0f}  "
              f"conv {float(m.get('conversions', 0)):>6.1f}")


def cmd_quota(args: argparse.Namespace) -> None:
    """Show today's local operation usage vs the daily cap."""
    used = _quota_read(args.account)
    cap = _quota_cap()
    data = {
        "account": args.account or "default",
        "date": _today(),
        "operations_used": used,
        "daily_cap": cap,
        "remaining": max(0, cap - used),
        "pct": round(used / cap * 100, 1) if cap else 0,
    }
    if args.json:
        _output_json(data)
    else:
        print(f"{data['account']} — {used:,}/{cap:,} ops today "
              f"({data['pct']}%), {data['remaining']:,} remaining")
        print("Note: each Search/SearchStream request = 1 op, each mutate op = 1; "
              "dry-runs aren't counted. Standard Access has no daily cap — raise "
              "GOOGLE_ADS_DAILY_OP_CAP. For the authoritative number see Cloud Console.")


# ===========================================================================
# MUTATIONS (Phase 2) — every mutation defaults to validate-only (dry run).
# Pass --confirm to actually write. A plan is always printed first.
# ===========================================================================
def _run_mutation(client, account, customer_id, *, service_name, method_name,
                  request_type, operations, confirm):
    """Execute a mutate request. validate_only=True unless confirm is set."""
    service = client.get_service(service_name)
    request = client.get_type(request_type)
    request.customer_id = customer_id
    for op in operations:
        request.operations.append(op)
    request.validate_only = not confirm

    # Only real writes count toward quota (validate-only dry-runs don't).
    if confirm:
        _quota_guard(account, len(operations))

    response = _execute_with_retry(
        lambda: getattr(service, method_name)(request=request),
        what=f"{method_name} {customer_id}",
    )
    if response is not None and confirm:
        _track_ops(account, len(operations))
    return response


def _show_result(response, confirm: bool, label: str) -> None:
    if not confirm:
        print(f"\n✅ VALIDACE OK — {label}.")
        print("   (dry-run: NIC nebylo zapsáno) — přidej --confirm pro skutečný zápis.")
        return
    print(f"\n✅ ZAPSÁNO — {label}:")
    results = getattr(response, "results", None) or []
    for r in results:
        print(f"   {r.resource_name}")


def _field_mask(client, obj):
    from google.api_core import protobuf_helpers
    return protobuf_helpers.field_mask(None, obj._pb)


def cmd_campaign_status(args: argparse.Namespace) -> None:
    """Enable / pause / remove a campaign."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = service.campaign_path(cid, args.campaign_id)
    campaign.status = client.enums.CampaignStatusEnum[args.status.upper()]
    client.copy_from(op.update_mask, _field_mask(client, campaign))

    print(f"PLÁN: kampaň {args.campaign_id} → status {args.status.upper()}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignService", method_name="mutate_campaigns",
                         request_type="MutateCampaignsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"kampaň {args.campaign_id} → {args.status.upper()}")


def cmd_budget_set(args: argparse.Namespace) -> None:
    """Set a campaign's daily budget (updates its CampaignBudget)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rows = _run_query(
        client, cid,
        f"SELECT campaign.id, campaign.name, campaign_budget.resource_name, "
        f"campaign_budget.amount_micros FROM campaign WHERE campaign.id = {args.campaign_id}",
        args.account,
    )
    if not rows:
        _die(f"Kampaň {args.campaign_id} nenalezena.")
    budget_rn = rows[0].campaign_budget.resource_name
    old = _micros(rows[0].campaign_budget.amount_micros)

    service = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    budget = op.update
    budget.resource_name = budget_rn
    budget.amount_micros = _to_micros(args.amount)
    client.copy_from(op.update_mask, _field_mask(client, budget))

    print(f"PLÁN: rozpočet kampaně '{rows[0].campaign.name}': "
          f"{old:,.0f} → {float(args.amount):,.0f} Kč/den")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignBudgetService", method_name="mutate_campaign_budgets",
                         request_type="MutateCampaignBudgetsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"rozpočet → {float(args.amount):,.0f} Kč/den")


def _apply_bidding(client, campaign, strategy: str, target_cpa, target_roas) -> str:
    """Set a standard bidding strategy on a campaign object. Returns a label."""
    if strategy == "manual_cpc":
        campaign.manual_cpc.enhanced_cpc_enabled = False
        return "Manual CPC"
    if strategy == "max_conversions":
        if target_cpa:
            campaign.maximize_conversions.target_cpa_micros = _to_micros(target_cpa)
            return f"Maximalizace konverzí (tCPA {float(target_cpa):,.0f} Kč)"
        client.copy_from(campaign.maximize_conversions, client.get_type("MaximizeConversions"))
        return "Maximalizace konverzí"
    if strategy == "max_conversion_value":
        if target_roas:
            campaign.maximize_conversion_value.target_roas = float(target_roas)
            return f"Maximalizace hodnoty konverzí (tROAS {float(target_roas):.2f})"
        client.copy_from(campaign.maximize_conversion_value, client.get_type("MaximizeConversionValue"))
        return "Maximalizace hodnoty konverzí"
    if strategy == "target_cpa":
        if not target_cpa:
            _die("target_cpa strategie vyžaduje --target-cpa")
        campaign.target_cpa.target_cpa_micros = _to_micros(target_cpa)
        return f"Cílová CPA {float(target_cpa):,.0f} Kč"
    if strategy == "target_roas":
        if not target_roas:
            _die("target_roas strategie vyžaduje --target-roas")
        campaign.target_roas.target_roas = float(target_roas)
        return f"Cílová ROAS {float(target_roas):.2f}"
    _die(f"Neznámá strategie: {strategy}")
    return ""


def cmd_bidding_set(args: argparse.Namespace) -> None:
    """Switch a campaign's bidding strategy."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    campaign = op.update
    campaign.resource_name = service.campaign_path(cid, args.campaign_id)
    label = _apply_bidding(client, campaign, args.strategy, args.target_cpa, args.target_roas)
    client.copy_from(op.update_mask, _field_mask(client, campaign))

    print(f"PLÁN: kampaň {args.campaign_id} → bidding: {label}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignService", method_name="mutate_campaigns",
                         request_type="MutateCampaignsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"bidding → {label}")


def cmd_campaign_create(args: argparse.Namespace) -> None:
    """Create a SEARCH campaign + its budget atomically (starts PAUSED)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    budget_service = client.get_service("CampaignBudgetService")
    campaign_service = client.get_service("CampaignService")
    budget_rn = budget_service.campaign_budget_path(cid, "-1")  # temp id

    ops = []
    mo_budget = client.get_type("MutateOperation")
    b = mo_budget.campaign_budget_operation.create
    b.name = f"{args.name} – budget"
    b.amount_micros = _to_micros(args.budget)
    b.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = False
    b.resource_name = budget_rn
    ops.append(mo_budget)

    mo_campaign = client.get_type("MutateOperation")
    c = mo_campaign.campaign_operation.create
    c.name = args.name
    c.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
    c.status = client.enums.CampaignStatusEnum.PAUSED
    c.campaign_budget = budget_rn
    _apply_bidding(client, c, args.bidding, args.target_cpa, args.target_roas)
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = True
    c.network_settings.target_content_network = False
    c.network_settings.target_partner_search_network = False
    c.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )
    ops.append(mo_campaign)

    label = _apply_bidding(client, client.get_type("Campaign"), args.bidding, args.target_cpa, args.target_roas)
    print(f"PLÁN: nová SEARCH kampaň '{args.name}' (PAUSED), "
          f"rozpočet {float(args.budget):,.0f} Kč/den, bidding {label}")

    service = client.get_service("GoogleAdsService")
    request = client.get_type("MutateGoogleAdsRequest")
    request.customer_id = cid
    request.mutate_operations.extend(ops)
    request.validate_only = not args.confirm
    if args.confirm:
        _quota_guard(args.account, len(ops))
    resp = _execute_with_retry(lambda: service.mutate(request=request),
                               what=f"campaign-create {cid}")
    if resp is None:
        return
    if args.confirm:
        _track_ops(args.account, len(ops))
        print("\n✅ ZAPSÁNO:")
        for r in resp.mutate_operation_responses:
            rn = (r.campaign_result.resource_name if r._pb.HasField("campaign_result")
                  else r.campaign_budget_result.resource_name if r._pb.HasField("campaign_budget_result")
                  else "")
            if rn:
                print(f"   {rn}")
    else:
        print("\n✅ VALIDACE OK — kampaň + rozpočet. (dry-run: nic nezapsáno) — přidej --confirm.")


def cmd_ad_group_create(args: argparse.Namespace) -> None:
    """Create an ad group in a campaign."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    campaign_service = client.get_service("CampaignService")
    op = client.get_type("AdGroupOperation")
    ag = op.create
    ag.name = args.name
    ag.campaign = campaign_service.campaign_path(cid, args.campaign)
    ag.status = client.enums.AdGroupStatusEnum.ENABLED
    ag.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    if args.cpc:
        ag.cpc_bid_micros = _to_micros(args.cpc)

    print(f"PLÁN: nová ad group '{args.name}' v kampani {args.campaign}"
          + (f", CPC {float(args.cpc):,.0f} Kč" if args.cpc else ""))
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupService", method_name="mutate_ad_groups",
                         request_type="MutateAdGroupsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"ad group '{args.name}'")


# Inline pin syntax: "AI First @H1" pins to HEADLINE_1; "text @D1" to DESCRIPTION_1.
# Pinning to position 1 is how you keep your brand/domain always visible — the
# fix for Limited Ad Serving "generic / unclear brand" flags.
_PIN_MAP = {
    "H1": "HEADLINE_1", "H2": "HEADLINE_2", "H3": "HEADLINE_3",
    "D1": "DESCRIPTION_1", "D2": "DESCRIPTION_2",
}


def _split_pin(raw: str) -> tuple[str, str | None]:
    """'AI First @H1' -> ('AI First', 'HEADLINE_1'); 'text' -> ('text', None)."""
    s = raw.strip()
    if " @" in s:
        base, _, tag = s.rpartition(" @")
        tag = tag.strip().upper()
        if tag in _PIN_MAP:
            return base.strip(), _PIN_MAP[tag]
    return s, None


def cmd_rsa_create(args: argparse.Namespace) -> None:
    """Create a responsive search ad. Headlines/descriptions are pipe-separated.

    Pin an asset with a trailing ` @H1`/`@H2`/`@H3` (headlines) or ` @D1`/`@D2`
    (descriptions) — e.g. `AI First @H1` keeps the brand in position 1.
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    headlines = [_split_pin(h) for h in args.headlines.split("|") if h.strip()]
    descriptions = [_split_pin(d) for d in args.descriptions.split("|") if d.strip()]
    if not (3 <= len(headlines) <= 15):
        _die(f"RSA potřebuje 3–15 headlines (máš {len(headlines)}).")
    if not (2 <= len(descriptions) <= 4):
        _die(f"RSA potřebuje 2–4 descriptions (máš {len(descriptions)}).")
    too_long_h = [t for t, _ in headlines if len(t) > 30]
    too_long_d = [t for t, _ in descriptions if len(t) > 90]
    if too_long_h:
        _die(f"Headlines max 30 znaků, překračují: {too_long_h}")
    if too_long_d:
        _die(f"Descriptions max 90 znaků, překračují: {too_long_d}")
    bad_h = [t for t, p in headlines if p and not p.startswith("HEADLINE")]
    bad_d = [t for t, p in descriptions if p and not p.startswith("DESCRIPTION")]
    if bad_h:
        _die(f"Headline lze připnout jen na H1/H2/H3: {bad_h}")
    if bad_d:
        _die(f"Description lze připnout jen na D1/D2: {bad_d}")

    ag_service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupAdOperation")
    aga = op.create
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad_group = ag_service.ad_group_path(cid, args.ad_group)
    aga.ad.final_urls.append(args.final_url)
    for text, pin in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        if pin:
            asset.pinned_field = client.enums.ServedAssetFieldTypeEnum[pin]
        aga.ad.responsive_search_ad.headlines.append(asset)
    for text, pin in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        if pin:
            asset.pinned_field = client.enums.ServedAssetFieldTypeEnum[pin]
        aga.ad.responsive_search_ad.descriptions.append(asset)
    if args.path1:
        aga.ad.responsive_search_ad.path1 = args.path1
    if args.path2:
        aga.ad.responsive_search_ad.path2 = args.path2

    pins = [f"{t}→{p}" for t, p in headlines + descriptions if p]
    print(f"PLÁN: nová RSA v ad group {args.ad_group} — "
          f"{len(headlines)} headlines, {len(descriptions)} descriptions, URL {args.final_url}")
    if pins:
        print(f"      připnuto: {', '.join(pins)}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupAdService", method_name="mutate_ad_group_ads",
                         request_type="MutateAdGroupAdsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, "responsive search ad")


def cmd_keyword_add(args: argparse.Namespace) -> None:
    """Batch-add positive keywords to an ad group from a JSON array.

    JSON: [{"text": "vibe coding kurz", "match_type": "phrase", "cpc": 25}, ...]
    match_type: exact | phrase | broad (default broad)
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    ag_service = client.get_service("AdGroupService")
    try:
        keywords = json.loads(args.keywords_json)
    except json.JSONDecodeError as ex:
        _die(f"Neplatný JSON: {ex}")

    ops = []
    for kw in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        crit = op.create
        crit.ad_group = ag_service.ad_group_path(cid, args.ad_group)
        crit.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        crit.keyword.text = kw["text"]
        crit.keyword.match_type = client.enums.KeywordMatchTypeEnum[
            kw.get("match_type", "broad").upper()
        ]
        if kw.get("cpc"):
            crit.cpc_bid_micros = _to_micros(kw["cpc"])
        ops.append(op)

    print(f"PLÁN: přidat {len(ops)} klíčových slov do ad group {args.ad_group}:")
    for kw in keywords:
        print(f"   [{kw.get('match_type', 'broad'):<6}] {kw['text']}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupCriterionService", method_name="mutate_ad_group_criteria",
                         request_type="MutateAdGroupCriteriaRequest", operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"{len(ops)} klíčových slov")


def cmd_negative_add(args: argparse.Namespace) -> None:
    """Add negative keywords at ad-group OR campaign level."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    match_type = client.enums.KeywordMatchTypeEnum[args.match_type.upper()]
    terms = [t.strip() for t in args.keywords.split(",") if t.strip()]
    if not terms:
        _die("Žádná klíčová slova (--keywords).")

    if args.ad_group:
        ag_service = client.get_service("AdGroupService")
        ops = []
        for t in terms:
            op = client.get_type("AdGroupCriterionOperation")
            crit = op.create
            crit.ad_group = ag_service.ad_group_path(cid, args.ad_group)
            crit.negative = True
            crit.keyword.text = t
            crit.keyword.match_type = match_type
            ops.append(op)
        scope = f"ad group {args.ad_group}"
        svc, method, req = ("AdGroupCriterionService", "mutate_ad_group_criteria",
                            "MutateAdGroupCriteriaRequest")
    elif args.campaign:
        c_service = client.get_service("CampaignService")
        ops = []
        for t in terms:
            op = client.get_type("CampaignCriterionOperation")
            crit = op.create
            crit.campaign = c_service.campaign_path(cid, args.campaign)
            crit.negative = True
            crit.keyword.text = t
            crit.keyword.match_type = match_type
            ops.append(op)
        scope = f"kampaň {args.campaign}"
        svc, method, req = ("CampaignCriterionService", "mutate_campaign_criteria",
                            "MutateCampaignCriteriaRequest")
    else:
        _die("Zadej --ad-group NEBO --campaign.")
        return

    print(f"PLÁN: přidat {len(ops)} negativ ({args.match_type}) na {scope}:")
    for t in terms:
        print(f"   −{t}")
    resp = _run_mutation(client, args.account, cid, service_name=svc, method_name=method,
                         request_type=req, operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"{len(ops)} negativ na {scope}")


def cmd_keyword_remove(args: argparse.Namespace) -> None:
    """Remove ad-group keyword criteria by 'adGroupId~criterionId' fragments."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    frags = [f.strip() for f in args.criteria.split(",") if f.strip()]
    if not frags:
        _die("Zadej --criteria 'adGroupId~criterionId,...'")
    ops = []
    for fr in frags:
        op = client.get_type("AdGroupCriterionOperation")
        op.remove = f"customers/{cid}/adGroupCriteria/{fr}"
        ops.append(op)
    print(f"PLÁN: odebrat {len(ops)} klíčových slov:")
    for fr in frags:
        print(f"   − {fr}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupCriterionService", method_name="mutate_ad_group_criteria",
                         request_type="MutateAdGroupCriteriaRequest", operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"odebráno {len(ops)} klíčových slov")


def cmd_ad_status(args: argparse.Namespace) -> None:
    """Enable / pause / remove a single ad within an ad group."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("AdGroupAdOperation")
    rn = f"customers/{cid}/adGroupAds/{args.ad_group_id}~{args.ad_id}"
    if args.status == "removed":
        # REMOVED cannot be set via an update — it requires a remove operation.
        op.remove = rn
    else:
        aga = op.update
        aga.resource_name = rn
        aga.status = client.enums.AdGroupAdStatusEnum[args.status.upper()]
        client.copy_from(op.update_mask, _field_mask(client, aga))
    print(f"PLÁN: reklama {args.ad_id} (sestava {args.ad_group_id}) → status {args.status.upper()}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupAdService", method_name="mutate_ad_group_ads",
                         request_type="MutateAdGroupAdsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"reklama {args.ad_id} → {args.status.upper()}")


def cmd_ad_update_url(args: argparse.Namespace) -> None:
    """Update the Final URL on an existing ad (keeps the ad's performance history)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    service = client.get_service("AdService")
    op = client.get_type("AdOperation")
    ad = op.update
    ad.resource_name = service.ad_path(cid, args.ad_id)
    ad.final_urls.append(args.final_url)
    client.copy_from(op.update_mask, _field_mask(client, ad))

    print(f"PLÁN: reklama {args.ad_id} → Final URL: {args.final_url}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdService", method_name="mutate_ads",
                         request_type="MutateAdsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"reklama {args.ad_id} → {args.final_url}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="google_ads_cli",
        description="Google Ads CLI (read-only foundation). Search campaigns, reporting, keyword research.",
    )
    p.add_argument("--account", help="Named account profile from .env (default: default)")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="One-time OAuth flow → generate a refresh token").set_defaults(func=cmd_auth)

    sub.add_parser("accounts", help="List accessible accounts under the MCC").set_defaults(func=cmd_accounts)

    sp = sub.add_parser("campaigns", help="List search campaigns")
    sp.add_argument("customer_id", help="Customer ID (with or without dashes)")
    sp.add_argument("--status", choices=["enabled", "paused", "removed"], help="Filter by status")
    sp.set_defaults(func=cmd_campaigns)

    sp = sub.add_parser("query", help="Run an arbitrary GAQL query")
    sp.add_argument("customer_id")
    sp.add_argument("--gaql", required=True, help="GAQL query string")
    sp.set_defaults(func=cmd_query)

    sp = sub.add_parser("report", help="Preset performance report")
    sp.add_argument("customer_id")
    sp.add_argument("--entity", default="campaign", help="campaign | ad_group | keyword")
    sp.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    sp.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("keywords-research", help="Keyword Planner ideas (volume/competition/CPC)")
    sp.add_argument("customer_id")
    sp.add_argument("--seed", required=True, help="Comma-separated seed keywords")
    sp.add_argument("--language", default=DEFAULT_LANGUAGE_ID, help=f"Language constant ID (default {DEFAULT_LANGUAGE_ID}=Czech)")
    sp.add_argument("--geo", default=DEFAULT_GEO_TARGET_ID, help=f"Geo target constant ID (default {DEFAULT_GEO_TARGET_ID}=Czech Republic)")
    sp.add_argument("--limit", type=int, default=100, help="Max ideas to show")
    sp.set_defaults(func=cmd_keywords_research)

    sp = sub.add_parser("search-terms", help="Actual search queries (source for negatives)")
    sp.add_argument("customer_id")
    sp.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    sp.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    sp.set_defaults(func=cmd_search_terms)

    sub.add_parser("quota", help="Show today's operation usage vs daily cap").set_defaults(func=cmd_quota)

    # --- Mutations (Phase 2): all default to validate-only; --confirm writes ---
    def _bidding_args(parser):
        parser.add_argument("--strategy", required=True,
                            choices=["manual_cpc", "max_conversions", "max_conversion_value",
                                     "target_cpa", "target_roas"])
        parser.add_argument("--target-cpa", dest="target_cpa", type=float, help="Target CPA in CZK")
        parser.add_argument("--target-roas", dest="target_roas", type=float, help="Target ROAS (e.g. 2.5)")

    sp = sub.add_parser("campaign-status", help="Enable/pause/remove a campaign [write]")
    sp.add_argument("customer_id")
    sp.add_argument("campaign_id")
    sp.add_argument("--status", required=True, choices=["enabled", "paused", "removed"])
    sp.add_argument("--confirm", action="store_true", help="Actually write (default: dry-run)")
    sp.set_defaults(func=cmd_campaign_status)

    sp = sub.add_parser("budget-set", help="Set a campaign's daily budget (CZK) [write]")
    sp.add_argument("customer_id")
    sp.add_argument("campaign_id")
    sp.add_argument("--amount", required=True, type=float, help="Daily budget in CZK")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_budget_set)

    sp = sub.add_parser("bidding-set", help="Switch a campaign's bidding strategy [write]")
    sp.add_argument("customer_id")
    sp.add_argument("campaign_id")
    _bidding_args(sp)
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_bidding_set)

    sp = sub.add_parser("campaign-create", help="Create a SEARCH campaign + budget (PAUSED) [write]")
    sp.add_argument("customer_id")
    sp.add_argument("--name", required=True)
    sp.add_argument("--budget", required=True, type=float, help="Daily budget in CZK")
    sp.add_argument("--bidding", default="manual_cpc",
                    choices=["manual_cpc", "max_conversions", "max_conversion_value",
                             "target_cpa", "target_roas"])
    sp.add_argument("--target-cpa", dest="target_cpa", type=float)
    sp.add_argument("--target-roas", dest="target_roas", type=float)
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_campaign_create)

    sp = sub.add_parser("ad-group-create", help="Create an ad group [write]")
    sp.add_argument("customer_id")
    sp.add_argument("--campaign", required=True, help="Campaign ID")
    sp.add_argument("--name", required=True)
    sp.add_argument("--cpc", type=float, help="Default CPC bid in CZK")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_ad_group_create)

    sp = sub.add_parser("rsa-create", help="Create a responsive search ad [write]")
    sp.add_argument("customer_id")
    sp.add_argument("--ad-group", dest="ad_group", required=True, help="Ad group ID")
    sp.add_argument("--headlines", required=True,
                    help="Pipe-separated, 3–15 items, ≤30 chars each. Pin with a trailing "
                         "' @H1'/'@H2'/'@H3' (e.g. 'AI First @H1' keeps the brand in position 1).")
    sp.add_argument("--descriptions", required=True,
                    help="Pipe-separated, 2–4 items, ≤90 chars each. Pin with ' @D1'/'@D2'.")
    sp.add_argument("--final-url", dest="final_url", required=True)
    sp.add_argument("--path1")
    sp.add_argument("--path2")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_rsa_create)

    sp = sub.add_parser("keyword-add", help="Batch-add positive keywords (JSON) [write]")
    sp.add_argument("customer_id")
    sp.add_argument("--ad-group", dest="ad_group", required=True, help="Ad group ID")
    sp.add_argument("--keywords-json", dest="keywords_json", required=True,
                    help='JSON array: [{"text":"...","match_type":"phrase","cpc":25}]')
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_keyword_add)

    sp = sub.add_parser("negative-add", help="Add negative keywords (ad-group or campaign) [write]")
    sp.add_argument("customer_id")
    sp.add_argument("--ad-group", dest="ad_group", help="Ad group ID (ad-group-level negatives)")
    sp.add_argument("--campaign", help="Campaign ID (campaign-level negatives)")
    sp.add_argument("--keywords", required=True, help="Comma-separated negative terms")
    sp.add_argument("--match-type", dest="match_type", default="phrase",
                    choices=["exact", "phrase", "broad"])
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_negative_add)

    sp = sub.add_parser("ad-update-url", help="Update Final URL on an existing ad [write]")
    sp.add_argument("customer_id")
    sp.add_argument("ad_id")
    sp.add_argument("--final-url", dest="final_url", required=True)
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_ad_update_url)

    sp = sub.add_parser("keyword-remove", help="Remove ad-group keyword criteria [write]")
    sp.add_argument("customer_id")
    sp.add_argument("--criteria", required=True, help="Comma-separated 'adGroupId~criterionId' fragments")
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_keyword_remove)

    sp = sub.add_parser("ad-status", help="Enable/pause/remove a single ad [write]")
    sp.add_argument("customer_id")
    sp.add_argument("ad_group_id")
    sp.add_argument("ad_id")
    sp.add_argument("--status", required=True, choices=["enabled", "paused", "removed"])
    sp.add_argument("--confirm", action="store_true")
    sp.set_defaults(func=cmd_ad_status)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
