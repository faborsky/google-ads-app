"""pulse — account-wide digest in 5 GAQL requests (5 ops):

totals + per-campaign metrics + deltas vs the previous equal-length window +
top movers + optimization score + Google recommendations summary + policy
problems. Designed to replace chaining campaigns/report/query for the daily
check — a compact, pre-aggregated, token-cheap overview.

Window ends YESTERDAY (today's data is incomplete). Low-volume accounts: treat
a 7-day pulse as a glance only — decisions belong on 60–90 day windows.
"""
from __future__ import annotations

import argparse
import datetime as _dt
from collections import Counter

from gads.api import _clean_id, _get_client, _run_query
from gads.formatting import _micros, _output_json, _pct


def _campaign_metrics(client, cid, account, date_from, date_to) -> dict[str, dict]:
    gaql = f"""
        SELECT campaign.id, campaign.name, campaign.status,
               campaign.optimization_score, campaign.advertising_channel_type,
               campaign_budget.amount_micros,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.conversions, metrics.conversions_value,
               metrics.all_conversions,
               metrics.search_budget_lost_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
          AND campaign.status != 'REMOVED'
    """
    out: dict[str, dict] = {}
    for r in _run_query(client, cid, gaql, account):
        m = r.metrics
        out[str(r.campaign.id)] = {
            "id": str(r.campaign.id),
            "name": r.campaign.name,
            "status": r.campaign.status.name,
            "channel": r.campaign.advertising_channel_type.name,
            "optimization_score": round(r.campaign.optimization_score, 3) or None,
            "daily_budget": _micros(r.campaign_budget.amount_micros),
            "impressions": m.impressions,
            "clicks": m.clicks,
            "cost": round(_micros(m.cost_micros), 2),
            "conversions": round(m.conversions, 1),
            "conversions_value": round(m.conversions_value, 2),
            "all_conversions": round(m.all_conversions, 1),
            "budget_lost_is": round(m.search_budget_lost_impression_share, 3),
        }
    return out


def _totals(campaigns: dict[str, dict]) -> dict:
    t = {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0,
         "conversions_value": 0.0, "all_conversions": 0.0}
    for c in campaigns.values():
        for k in t:
            t[k] += c[k]
    t["cost"] = round(t["cost"], 2)
    t["ctr_pct"] = _pct(t["clicks"], t["impressions"])
    t["cpa"] = round(t["cost"] / t["conversions"], 1) if t["conversions"] else None
    t["roas"] = round(t["conversions_value"] / t["cost"], 2) if t["cost"] else None
    return t


def _delta(cur, prev):
    if prev in (0, 0.0, None):
        return None
    return round((cur - prev) / prev * 100, 1)


def cmd_pulse(args: argparse.Namespace) -> None:
    """Account digest: totals, per-campaign, deltas, movers, opt score,
    recommendations, policy problems — 5 GAQL requests total."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)

    days = args.days or 7
    if args.date_from and args.date_to:
        d_to = _dt.date.fromisoformat(args.date_to)
        d_from = _dt.date.fromisoformat(args.date_from)
        days = (d_to - d_from).days + 1
    else:
        d_to = _dt.date.today() - _dt.timedelta(days=1)
        d_from = d_to - _dt.timedelta(days=days - 1)
    p_to = d_from - _dt.timedelta(days=1)
    p_from = p_to - _dt.timedelta(days=days - 1)

    current = _campaign_metrics(client, cid, args.account, d_from.isoformat(), d_to.isoformat())
    previous = ({} if args.no_compare else
                _campaign_metrics(client, cid, args.account, p_from.isoformat(), p_to.isoformat()))

    cust_rows = _run_query(client, cid, """
        SELECT customer.descriptive_name, customer.currency_code,
               customer.optimization_score FROM customer""", args.account)
    cust = cust_rows[0].customer if cust_rows else None

    rec_rows = _run_query(client, cid,
                          "SELECT recommendation.type FROM recommendation", args.account)
    recommendations = Counter(r.recommendation.type_.name for r in rec_rows)

    policy_rows = _run_query(client, cid, """
        SELECT ad_group_ad.policy_summary.approval_status FROM ad_group_ad
        WHERE ad_group_ad.status != 'REMOVED'
          AND ad_group_ad.policy_summary.approval_status != 'APPROVED'
    """, args.account)
    policy_problems = Counter(
        r.ad_group_ad.policy_summary.approval_status.name for r in policy_rows)

    tot_cur = _totals(current)
    tot_prev = _totals(previous) if previous else None

    campaigns_out = []
    for cids in sorted(current, key=lambda k: -current[k]["cost"]):
        c = dict(current[cids])
        p = previous.get(cids)
        c["cost_delta_pct"] = _delta(c["cost"], p["cost"]) if p else None
        c["conversions_delta_pct"] = _delta(c["conversions"], p["conversions"]) if p else None
        campaigns_out.append(c)

    movers = sorted(
        (c for c in campaigns_out if c["cost_delta_pct"] is not None),
        key=lambda c: abs(c["cost_delta_pct"]), reverse=True)[:3]

    warnings = []
    if tot_cur["conversions"] == 0 and tot_cur["all_conversions"] > 0:
        warnings.append("Primary konverze 0, ale all_conversions > 0 — klíčová akce "
                        "je nejspíš Secondary/HIDDEN místo Primary (zkontroluj měření).")
    capped = [c["name"] for c in campaigns_out
              if c["status"] == "ENABLED" and c["budget_lost_is"] > 0.1]
    if capped:
        warnings.append(f"Rozpočtem limitované kampaně (lost IS >10 %): {', '.join(capped)}")

    data = {
        "account": {
            "id": cid,
            "name": cust.descriptive_name if cust else None,
            "currency": cust.currency_code if cust else None,
            "optimization_score": (round(cust.optimization_score, 3)
                                   if cust and cust.optimization_score else None),
        },
        "window": {"from": d_from.isoformat(), "to": d_to.isoformat(), "days": days},
        "previous_window": (None if args.no_compare else
                            {"from": p_from.isoformat(), "to": p_to.isoformat()}),
        "totals": tot_cur,
        "totals_previous": tot_prev,
        "campaigns": campaigns_out,
        "top_movers": [c["id"] for c in movers],
        "recommendations": dict(recommendations),
        "policy_problems": dict(policy_problems),
        "warnings": warnings,
    }
    if args.json:
        _output_json(data)
        return

    acc = data["account"]
    print(f"📊 {acc['name'] or cid} ({acc['currency'] or '?'}) — pulse "
          f"{d_from} → {d_to} ({days} d)")
    if acc["optimization_score"] is not None:
        print(f"   Optimization score: {acc['optimization_score'] * 100:.0f} %")

    def line(label, cur, prev, fmt=",.0f"):
        d = _delta(cur, prev) if prev is not None else None
        ds = f"  ({'+' if d >= 0 else ''}{d}%)" if d is not None else ""
        print(f"   {label:<12} {cur:>12{fmt}}{ds}")

    tp = tot_prev or {}
    print("— Totály (vs. předchozí okno):")
    line("Imprese", tot_cur["impressions"], tp.get("impressions"))
    line("Prokliky", tot_cur["clicks"], tp.get("clicks"))
    line("Cena", tot_cur["cost"], tp.get("cost"))
    line("Konverze", tot_cur["conversions"], tp.get("conversions"), fmt=",.1f")
    line("Hodnota", tot_cur["conversions_value"], tp.get("conversions_value"))
    if tot_cur["cpa"]:
        print(f"   {'CPA':<12} {tot_cur['cpa']:>12,.0f}")
    if tot_cur["roas"]:
        print(f"   {'ROAS':<12} {tot_cur['roas']:>12,.2f}")

    print("— Kampaně (řazeno dle ceny):")
    for c in campaigns_out:
        d = c["cost_delta_pct"]
        ds = f" ({'+' if d >= 0 else ''}{d}%)" if d is not None else ""
        opt = f" opt {c['optimization_score'] * 100:.0f}%" if c["optimization_score"] else ""
        print(f"   {c['status']:<8} {c['name'][:34]:<34} cena {c['cost']:>9,.0f}{ds}  "
              f"conv {c['conversions']:>5.1f}{opt}")

    if recommendations:
        recs = ", ".join(f"{t}×{n}" if n > 1 else t for t, n in recommendations.most_common(5))
        print(f"— Doporučení Googlu ({sum(recommendations.values())}): {recs}")
    if policy_problems:
        pp = ", ".join(f"{k}: {v}" for k, v in policy_problems.items())
        print(f"— ⚠️ Policy problémy inzerátů: {pp}  (detail: `ad-policy --only-problems`)")
    for w in warnings:
        print(f"— ⚠️ {w}")
    if not previous and not args.no_compare:
        print("(předchozí okno bez dat — delty nejsou)")
