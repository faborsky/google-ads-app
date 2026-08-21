"""Reporting: arbitrary GAQL, preset reports, change history."""
from __future__ import annotations

import argparse
import datetime as _dt
import json

from gads.api import _clean_id, _get_client, _run_query
from gads.formatting import _die, _err, _micros, _output_json, _row_to_dict


def cmd_query(args: argparse.Namespace) -> None:
    """Run an arbitrary GAQL query (the reporting core)."""
    client = _get_client(args.account)
    rows = _run_query(client, _clean_id(args.customer_id), args.gaql, args.account)
    if args.json:
        _output_json([_row_to_dict(r) for r in rows])
    else:
        for r in rows:
            print(json.dumps(_row_to_dict(r), ensure_ascii=False))
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

    out = [_row_to_dict(r) for r in rows]
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


def cmd_changes(args: argparse.Namespace) -> None:
    """Change history. Default = change_event (who changed what, old→new, ≤30 days).

    --sweep = change_status (what moved, ≤90 days, no field values — cheap sweep).
    Both resources REQUIRE a date filter and LIMIT (max 10 000).
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    days = args.days or (89 if args.sweep else 14)
    max_days = 90 if args.sweep else 30
    if days >= max_days:
        _die(f"{'change_status' if args.sweep else 'change_event'} podporuje jen "
             f"posledních {max_days} dní (chceš {days}).")
    limit = min(args.limit or 200, 10000)
    # change_event requires datetime bounds; end must be in the future-safe today+1
    start = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
    end = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()

    if args.sweep:
        gaql = f"""
            SELECT change_status.resource_name, change_status.last_change_date_time,
                   change_status.resource_type, change_status.resource_status,
                   change_status.campaign, change_status.ad_group
            FROM change_status
            WHERE change_status.last_change_date_time >= '{start}'
              AND change_status.last_change_date_time <= '{end}'
            ORDER BY change_status.last_change_date_time DESC
            LIMIT {limit}
        """
    else:
        gaql = f"""
            SELECT change_event.change_date_time, change_event.user_email,
                   change_event.client_type, change_event.change_resource_type,
                   change_event.change_resource_name, change_event.resource_change_operation,
                   change_event.changed_fields
            FROM change_event
            WHERE change_event.change_date_time >= '{start}'
              AND change_event.change_date_time <= '{end}'
            ORDER BY change_event.change_date_time DESC
            LIMIT {limit}
        """
    rows = _run_query(client, cid, gaql, args.account)
    out = [_row_to_dict(r) for r in rows]
    if len(out) >= limit:
        # The API REQUIRES a LIMIT here, so truncation is possible — say so
        # instead of silently returning a partial history.
        _err(f"⚠️  Vráceno přesně {limit} řádků = LIMIT — historie je nejspíš useknutá. "
             f"Zvyš --limit (max 10000) nebo zkrať --days.")
    if args.json:
        _output_json(out)
        return
    if not out:
        print(f"Žádné změny za posledních {days} dní.")
        return
    for r in out:
        if args.sweep:
            cs = r.get("changeStatus", {})
            target = cs.get("campaign") or cs.get("adGroup") or ""
            print(f"{cs.get('lastChangeDateTime', '?'):<20} {cs.get('resourceStatus', ''):<8} "
                  f"{cs.get('resourceType', ''):<18} {target}")
        else:
            ce = r.get("changeEvent", {})
            # MessageToDict renders a FieldMask as a comma-separated STRING
            cf = ce.get("changedFields") or ""
            fields = (cf if isinstance(cf, str)
                      else ", ".join(cf.get("paths", []))) or "-"
            print(f"{ce.get('changeDateTime', '?'):<20} {ce.get('userEmail', '?'):<28} "
                  f"{ce.get('resourceChangeOperation', ''):<7} "
                  f"{ce.get('changeResourceType', ''):<18} {fields[:60]}")
    _err(f"({len(out)} změn, okno {days} d)")
