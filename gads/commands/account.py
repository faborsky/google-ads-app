"""Account-level commands: accounts, quota, api-limits."""
from __future__ import annotations

import argparse

from gads.api import (_clean_id, _env, _get_client, _quota_cap, _quota_read,
                      _run_query, _today, _track_ops)
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
        "pct": _pct(used, cap),
    }
    if args.json:
        _output_json(data)
    else:
        print(f"{data['account']} — {used:,}/{cap:,} ops today "
              f"({data['pct']}%), {data['remaining']:,} remaining")
        print("Note: each Search/SearchStream request = 1 op, each mutate op = 1; "
              "dry-runs aren't counted. Standard Access has no daily cap — raise "
              "GOOGLE_ADS_DAILY_OP_CAP. For the authoritative number see Cloud Console.")


# Documented Google Ads API limits (docs, verified 2026-07-19) — the API has no
# runtime limits endpoint (unlike Sklik's api.limits), so these are constants.
_API_LIMITS = {
    "daily_ops_basic_access": 15000,
    "daily_ops_explorer_access": 2880,
    "daily_ops_standard_access": "unlimited",
    "search_request_ops": "1 op per Search/SearchStream request (regardless of rows)",
    "mutate_ops_per_request_max": 10000,
    "planning_services_qps": "1 QPS (Keyword Planner / GenerateKeywordIdeas)",
    "qps_metering": "per client CID + developer token; violation → RESOURCE_(TEMPORARILY_)EXHAUSTED",
    "retry_policy": "exponential back-off 5→10→20 s (honours Google's retry_delay), max 3 retries",
    "change_event_window_days": 30,
    "change_status_window_days": 90,
    "change_query_limit_max": 10000,
}


def cmd_api_limits(args: argparse.Namespace) -> None:
    """Documented API limits + live local quota usage (per account/day)."""
    used = _quota_read(args.account)
    cap = _quota_cap()
    data = {
        "account": args.account or "default",
        "date": _today(),
        "local_ops_used": used,
        "local_daily_cap": cap,
        "limits": _API_LIMITS,
    }
    if args.json:
        _output_json(data)
        return
    print(f"Lokální čerpání ({data['account']}, {data['date']}): "
          f"{used:,}/{cap:,} ops ({_pct(used, cap)}%)")
    print("\nDokumentované limity Google Ads API (ověřeno 2026-07-19):")
    for k, v in _API_LIMITS.items():
        print(f"  {k:<32} {v}")
    print("\nCap nastavíš v .env: GOOGLE_ADS_DAILY_OP_CAP (Basic 15000; Standard bez limitu).")
