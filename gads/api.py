"""Engine: credentials, client, quota guard, QPS retry, query & mutation runners.

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
    Planning services (Keyword Planner) are additionally capped at 1 QPS.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from gads.formatting import _die, _err

# Project root = parent of the gads/ package, so .env and .quota/ stay where
# they were in the single-file era.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

API_VERSION = "v24"
QUOTA_DIR = BASE_DIR / ".quota"
SCOPES = ["https://www.googleapis.com/auth/adwords"]

# Google Ads daily quota resets at midnight Pacific time, so the local op
# counter is bucketed by the Pacific date (not the machine's local date).
GOOGLE_TZ = ZoneInfo("America/Los_Angeles")

# Sensible defaults for Czech accounts.
DEFAULT_LANGUAGE_ID = "1021"      # Czech
DEFAULT_GEO_TARGET_ID = "2203"    # Czech Republic


def _today() -> str:
    """Current date in Google's quota timezone (Pacific), ISO format."""
    return _dt.datetime.now(GOOGLE_TZ).date().isoformat()


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
# Quota tracking — Basic Access = 15000 ops/day. Tracked locally per
# account/Pacific-day in .quota/. Search/SearchStream = 1 op per REQUEST
# (regardless of rows); each mutate operation = 1 op; validate-only dry-runs
# are free and not counted.
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


# ---------------------------------------------------------------------------
# Rate-limit retry (QPS) — RESOURCE_EXHAUSTED / RESOURCE_TEMPORARILY_EXHAUSTED
# ---------------------------------------------------------------------------
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


def _report_google_ads_exception(ex) -> None:
    msgs = []
    for error in ex.failure.errors:
        loc = ""
        if error.location and error.location.field_path_elements:
            loc = " on " + ".".join(e.field_name for e in error.location.field_path_elements)
        msgs.append(f"  - {error.message}{loc}")
    _die("Google Ads API request failed (request_id="
         + f"{ex.request_id}):\n" + "\n".join(msgs))


def _execute_with_retry(call, what: str):
    """Run an API call, retrying on quota/rate exhaustion with exponential
    back-off (honouring Google's suggested delay — the official guidance is
    5→10→20 s). Non-rate errors are reported and abort."""
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
# Query execution — a Search/SearchStream request = 1 op regardless of rows.
# ---------------------------------------------------------------------------
def _run_query(client, customer_id: str, gaql: str, account: str | None) -> list:
    service = client.get_service("GoogleAdsService")
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


# ---------------------------------------------------------------------------
# Mutations — every mutation defaults to validate-only (dry run); --confirm
# performs the real write. Only real writes count toward quota.
# ---------------------------------------------------------------------------
def _run_mutation(client, account, customer_id, *, service_name, method_name,
                  request_type, operations, confirm):
    """Execute a mutate request. validate_only=True unless confirm is set."""
    service = client.get_service(service_name)
    request = client.get_type(request_type)
    request.customer_id = customer_id
    for op in operations:
        request.operations.append(op)
    request.validate_only = not confirm

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


# ---------------------------------------------------------------------------
# Safety: Google Ads has NO undelete — REMOVED is permanent. The rescue brake
# is "PAUSED before REMOVED": removal is refused unless the entity is already
# paused (override with --force).
# ---------------------------------------------------------------------------
def _require_paused_before_remove(client, account, customer_id: str, *,
                                  gaql: str, entity_label: str, force: bool) -> None:
    """Refuse removal of an entity that isn't PAUSED (REMOVED is irreversible).

    `gaql` must select exactly one row whose first field path ends in `.status`.
    """
    if force:
        _err(f"⚠️  --force: přeskakuji pojistku PAUSED-před-REMOVED pro {entity_label}.")
        return
    rows = _run_query(client, customer_id, gaql, account)
    if not rows:
        _die(f"{entity_label} nenalezen(a).")
    row = rows[0]
    # walk to the status field of the first selected resource
    resource = gaql.split("FROM")[1].split()[0].strip()
    attr = {"ad_group_ad": "ad_group_ad"}.get(resource, resource)
    status = getattr(getattr(row, attr), "status").name
    if status != "PAUSED":
        _die(f"POJISTKA: {entity_label} má status {status}, ne PAUSED. REMOVED je "
             f"v Google Ads TRVALÉ (žádné obnovení). Nejdřív pauzni "
             f"(… --status paused --confirm), zkontroluj, a pak teprve maž. "
             f"Vědomé obejití: --force.")
