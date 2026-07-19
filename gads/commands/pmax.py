"""Performance Max — REPORTING ONLY (management would drag in the whole atomic
asset-group stack; different product surface than a search CLI).

PMax has no ad_group / ad_group_ad rows. Search terms come from
campaign_search_term_view (plain search_term_view excludes PMax).
Channel split via segments.ad_network_type works since v23.
"""
from __future__ import annotations

import argparse

from gads.api import _clean_id, _get_client, _run_query
from gads.formatting import _micros, _output_json


def cmd_pmax(args: argparse.Namespace) -> None:
    """PMax campaign metrics (with per-channel split via --channels)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    channel_seg = ", segments.ad_network_type" if args.channels else ""
    gaql = f"""
        SELECT campaign.id, campaign.name, campaign.status{channel_seg},
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.conversions, metrics.conversions_value
        FROM campaign
        WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
          AND campaign.status != 'REMOVED'
          AND segments.date BETWEEN '{args.date_from}' AND '{args.date_to}'
        ORDER BY metrics.cost_micros DESC
    """
    rows = _run_query(client, cid, gaql, args.account)
    out = []
    for r in rows:
        item = {
            "id": str(r.campaign.id),
            "name": r.campaign.name,
            "status": r.campaign.status.name,
            "impressions": r.metrics.impressions,
            "clicks": r.metrics.clicks,
            "cost": round(_micros(r.metrics.cost_micros), 2),
            "conversions": round(r.metrics.conversions, 1),
            "conversions_value": round(r.metrics.conversions_value, 2),
        }
        if args.channels:
            item["channel"] = r.segments.ad_network_type.name
        out.append(item)
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádné PMax kampaně (nebo žádná data v okně).")
        return
    for c in out:
        ch = f"  [{c['channel']}]" if args.channels else ""
        print(f"{c['id']:>12}  {c['status']:<8} cena {c['cost']:>10,.0f}  "
              f"conv {c['conversions']:>6.1f}  hodnota {c['conversions_value']:>10,.0f}  "
              f"{c['name']}{ch}")


def cmd_pmax_search_terms(args: argparse.Namespace) -> None:
    """Search terms of PMax campaigns (campaign_search_term_view)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    where = f"WHERE segments.date BETWEEN '{args.date_from}' AND '{args.date_to}'"
    if args.campaign:
        where += f" AND campaign.id = {args.campaign}"
    gaql = f"""
        SELECT campaign.name, campaign_search_term_view.search_term,
               metrics.impressions, metrics.clicks, metrics.conversions
        FROM campaign_search_term_view
        {where}
        ORDER BY metrics.clicks DESC
        LIMIT 500
    """
    rows = _run_query(client, cid, gaql, args.account)
    out = [{
        "campaign": r.campaign.name,
        "search_term": r.campaign_search_term_view.search_term,
        "impressions": r.metrics.impressions,
        "clicks": r.metrics.clicks,
        "conversions": round(r.metrics.conversions, 1),
    } for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádné search terms (PMax) v okně.")
        return
    for t in out:
        print(f"{t['search_term'][:50]:<50}  impr {t['impressions']:>7,}  "
              f"clicks {t['clicks']:>5}  conv {t['conversions']:>5.1f}")
