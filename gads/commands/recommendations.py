"""Google recommendations: list, apply, dismiss.

⚠️ Recommendations regenerate dynamically (daily or more often) — resource
names go STALE. List → apply/dismiss in the same session. Applying a keyword/ad
recommendation makes YOU responsible for its policy compliance. Apply/dismiss
are mutates (count toward daily quota).
"""
from __future__ import annotations

import argparse

from gads.api import _clean_id, _get_client, _run_query
from gads.formatting import _die, _micros, _output_json


def cmd_recommendations(args: argparse.Namespace) -> None:
    """List Google's recommendations with type, campaign and impact."""
    client = _get_client(args.account)
    # Nested impact/detail fields are NOT selectable in GAQL — whole
    # submessages are (verified live 2026-07-19).
    gaql = """
        SELECT recommendation.resource_name, recommendation.type,
               recommendation.dismissed, recommendation.campaign,
               recommendation.impact,
               recommendation.campaign_budget_recommendation,
               recommendation.keyword_recommendation
        FROM recommendation
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = []
    for r in rows:
        rec = r.recommendation
        item = {
            "resource_name": rec.resource_name,
            "type": rec.type_.name,
            "campaign": rec.campaign.split("/")[-1] if rec.campaign else None,
            "dismissed": rec.dismissed,
            "impact_clicks_delta": round(
                rec.impact.potential_metrics.clicks - rec.impact.base_metrics.clicks, 1),
            "impact_cost_delta": round(_micros(
                rec.impact.potential_metrics.cost_micros
                - rec.impact.base_metrics.cost_micros), 0),
        }
        if rec.type_.name == "CAMPAIGN_BUDGET":
            item["recommended_budget"] = _micros(
                rec.campaign_budget_recommendation.recommended_budget_amount_micros)
        if rec.type_.name == "KEYWORD":
            item["keyword"] = rec.keyword_recommendation.keyword.text
            item["match_type"] = rec.keyword_recommendation.keyword.match_type.name
        out.append(item)
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádná doporučení. ✅")
        return
    for i, rec in enumerate(out, 1):
        extra = ""
        if rec.get("recommended_budget"):
            extra = f"  → budget {rec['recommended_budget']:,.0f}"
        if rec.get("keyword"):
            extra = f"  → [{rec['match_type']}] {rec['keyword']}"
        camp = f"  (kampaň {rec['campaign']})" if rec["campaign"] else ""
        print(f"{i:>3}. {rec['type']:<40}{camp}{extra}")
        print(f"     {rec['resource_name']}")
    print("\nAplikuj: `recommendation-apply --resource <resource_name>`; "
          "zamítni: `recommendation-dismiss`. Resource names rychle stárnou.")


def _rec_ops(client, args, op_type: str):
    resources = [r.strip() for r in args.resource.split(",") if r.strip()]
    if not resources:
        _die("Zadej --resource (resource_name z `recommendations`, lze víc přes čárku).")
    ops = []
    for rn in resources:
        op = client.get_type(op_type)
        op.resource_name = rn
        ops.append(op)
    return ops, resources


def cmd_recommendation_apply(args: argparse.Namespace) -> None:
    """Apply recommendation(s) as Google suggests them (no parameter overrides
    — for a custom budget use budget-set instead of applying).

    ApplyRecommendationRequest has NO validate_only — dry-run = plan only."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    ops, resources = _rec_ops(client, args, "ApplyRecommendationOperation")

    print(f"PLÁN: aplikovat {len(ops)} doporučení:")
    for rn in resources:
        print(f"   {rn.split('/')[-1]}")
    if not args.confirm:
        print("\n(apply nemá validate_only — tohle je jen plán) — přidej --confirm.")
        return

    from gads.api import _execute_with_retry, _quota_guard, _track_ops
    service = client.get_service("RecommendationService")
    request = client.get_type("ApplyRecommendationRequest")
    request.customer_id = cid
    request.operations.extend(ops)
    _quota_guard(args.account, len(ops))
    resp = _execute_with_retry(
        lambda: service.apply_recommendation(request=request),
        what=f"apply-recommendation {cid}")
    if resp is None:
        return
    _track_ops(args.account, len(ops))
    print(f"\n✅ APLIKOVÁNO — {len(ops)} doporučení:")
    for r in resp.results:
        print(f"   {r.resource_name}")


def cmd_recommendation_dismiss(args: argparse.Namespace) -> None:
    """Dismiss recommendation(s) — hides them and stops them from dragging the
    optimization score down."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    resources = [r.strip() for r in args.resource.split(",") if r.strip()]
    if not resources:
        _die("Zadej --resource (resource_name z `recommendations`, lze víc přes čárku).")

    service = client.get_service("RecommendationService")
    request = client.get_type("DismissRecommendationRequest")
    request.customer_id = cid
    for rn in resources:
        op = client.get_type("DismissRecommendationRequest").DismissRecommendationOperation()
        op.resource_name = rn
        request.operations.append(op)

    print(f"PLÁN: zamítnout {len(resources)} doporučení:")
    for rn in resources:
        print(f"   {rn.split('/')[-1]}")
    if not args.confirm:
        # DismissRecommendationRequest has NO validate_only — dry-run = plan only.
        print("\n(dismiss nemá validate_only — tohle je jen plán) — přidej --confirm.")
        return
    from gads.api import _execute_with_retry, _quota_guard, _track_ops
    _quota_guard(args.account, len(resources))
    resp = _execute_with_retry(
        lambda: service.dismiss_recommendation(request=request),
        what=f"dismiss-recommendation {cid}")
    if resp is None:
        return
    _track_ops(args.account, len(resources))
    print(f"\n✅ ZAMÍTNUTO — {len(resources)} doporučení.")
