"""Account-level commands: accounts, quota, api-limits."""
from __future__ import annotations

import argparse

from gads.api import (API_VERSION, _clean_id, _env, _get_client, _quota_cap,
                      _quota_oldest_expiry, _quota_read, _run_query,
                      _track_ops)
from gads.formatting import _die, _output_json, _pct


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
        # Expand the whole MCC hierarchy (level 0 = the MCC itself, 1 = direct
        # children, 2+ = accounts under sub-managers) for names/currency/timezone.
        gaql = """
            SELECT customer_client.id, customer_client.descriptive_name,
                   customer_client.currency_code, customer_client.time_zone,
                   customer_client.manager, customer_client.level, customer_client.status
            FROM customer_client
            WHERE customer_client.status != 'CLOSED'
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
        accounts.sort(key=lambda a: (a["level"], a["name"] or ""))
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
            indent = "  " * int(a.get("level") or 0)
            print(f"{a['id']:>12}  {indent}{a['name']}{tag}  "
                  f"({a['currency']}, {a['time_zone']}, {a['status']})")
        else:
            print(a["resource_name"])


def cmd_quota(args: argparse.Namespace) -> None:
    """Show the local operation usage over the last 24 h vs the daily cap."""
    used = _quota_read(args.account)
    cap = _quota_cap()
    wait = _quota_oldest_expiry(args.account)
    data = {
        "account": args.account or "default",
        "window": "sliding 24 h",
        "operations_used": used,
        "daily_cap": cap,
        "remaining": max(0, cap - used),
        "pct": _pct(used, cap),
        "oldest_op_expires_in_min": round(wait / 60) if wait else None,
    }
    if args.json:
        _output_json(data)
    else:
        print(f"{data['account']} — {used:,}/{cap:,} ops za posledních 24 h "
              f"({data['pct']}%), zbývá {data['remaining']:,}")
        if wait:
            print(f"Nejstarší započtená operace vyprší za ~{wait / 60:.0f} min.")
        print("Pozn.: Search/SearchStream request = 1 op, každá mutate operace = 1 op; "
              "validate_only dry-runy počítáme taky (Google výjimku nedokumentuje). "
              "Google měří limit klouzavě za 24 h (ne kalendářní den). Standard Access "
              "denní cap nemá — zvyš GOOGLE_ADS_DAILY_OP_CAP. Autoritativní čísla: "
              "Cloud Console → APIs & Services → Google Ads API.")


# Documented Google Ads API limits (docs verified 2026-08-21) — the API has no
# runtime limits endpoint (unlike Sklik's api.limits), so these are constants.
_API_LIMITS = {
    "api_version": API_VERSION,
    "daily_ops_test_account_access": "15000 (test accounts only)",
    "daily_ops_explorer_access": "2880 on production accounts (15000 on test); "
                                 "Keyword Planner & planning services BLOCKED",
    "daily_ops_basic_access": 15000,
    "daily_ops_standard_access": "unlimited",
    "daily_window": "sliding 24 h per developer token (not a calendar day)",
    "search_request_ops": "1 op per Search/SearchStream request (regardless of rows)",
    "validate_only_requests": "not documented as exempt → the CLI counts them too",
    "mutate_ops_per_request_max": 10000,
    "grpc_response_max": "64 MB per response (select fewer fields / stream)",
    "planning_services_qps": "1 request/s per CID (Keyword Planner / GenerateKeywordIdeas)",
    "qps_metering": "token bucket per client CID + developer token; violation → "
                    "RESOURCE_EXHAUSTED / RESOURCE_TEMPORARILY_EXHAUSTED",
    "retry_policy": "exponential back-off 5→10→20 s (honours Google's retry_delay), "
                    "max 3 retries; transient transport errors retried for reads only",
    "change_event_window_days": 30,
    "change_status_window_days": 90,
    "change_query_limit_max": 10000,
}


def cmd_api_limits(args: argparse.Namespace) -> None:
    """Documented API limits + live local quota usage (last 24 h per account)."""
    used = _quota_read(args.account)
    cap = _quota_cap()
    data = {
        "account": args.account or "default",
        "window": "sliding 24 h",
        "local_ops_used": used,
        "local_daily_cap": cap,
        "limits": _API_LIMITS,
    }
    if args.json:
        _output_json(data)
        return
    print(f"Lokální čerpání ({data['account']}, posledních 24 h): "
          f"{used:,}/{cap:,} ops ({_pct(used, cap)}%)")
    print("\nDokumentované limity Google Ads API (ověřeno 2026-08-21):")
    for k, v in _API_LIMITS.items():
        print(f"  {k:<32} {v}")
    print("\nCap nastavíš v .env: GOOGLE_ADS_DAILY_OP_CAP (Basic 15000; Explorer 2880; "
          "Standard bez limitu).")
