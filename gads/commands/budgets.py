"""Budgets: set daily budget, list budgets (incl. shared + Google's recommended
amounts), create shared budgets, assign campaigns to a shared budget.

API quirk: `explicitly_shared` defaults to TRUE in API create ops (unlike the
UI) — the CLI always sets it explicitly. Shared → non-shared conversion is
impossible; non-shared → shared is one-way.
"""
from __future__ import annotations

import argparse

from gads.api import (_clean_id, _field_mask, _get_client, _run_mutation,
                      _run_query, _show_result)
from gads.formatting import _die, _micros, _output_json, _to_micros


def cmd_budgets(args: argparse.Namespace) -> None:
    """List campaign budgets (shared ones incl. attached-campaign count)."""
    client = _get_client(args.account)
    gaql = """
        SELECT campaign_budget.id, campaign_budget.name,
               campaign_budget.amount_micros, campaign_budget.explicitly_shared,
               campaign_budget.reference_count, campaign_budget.status,
               campaign_budget.has_recommended_budget,
               campaign_budget.recommended_budget_amount_micros
        FROM campaign_budget
        WHERE campaign_budget.status != 'REMOVED'
        ORDER BY campaign_budget.amount_micros DESC
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = [{
        "id": str(r.campaign_budget.id),
        "name": r.campaign_budget.name,
        "daily_amount": _micros(r.campaign_budget.amount_micros),
        "shared": r.campaign_budget.explicitly_shared,
        "campaigns_attached": r.campaign_budget.reference_count,
        "has_recommended_budget": r.campaign_budget.has_recommended_budget,
        "recommended_amount": _micros(r.campaign_budget.recommended_budget_amount_micros),
    } for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("No budgets found.")
        return
    for b in out:
        rec = (f"  → Google doporučuje {b['recommended_amount']:,.0f}"
               if b["has_recommended_budget"] else "")
        tag = " [SHARED]" if b["shared"] else ""
        print(f"{b['id']:>12}  {b['daily_amount']:>10,.0f}/den  "
              f"kampaní: {b['campaigns_attached']}  {b['name']}{tag}{rec}")


def cmd_budget_set(args: argparse.Namespace) -> None:
    """Set a campaign's daily budget (updates its CampaignBudget)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rows = _run_query(
        client, cid,
        f"SELECT campaign.id, campaign.name, campaign_budget.resource_name, "
        f"campaign_budget.amount_micros, campaign_budget.explicitly_shared "
        f"FROM campaign WHERE campaign.id = {args.campaign_id}",
        args.account,
    )
    if not rows:
        _die(f"Kampaň {args.campaign_id} nenalezena.")
    budget_rn = rows[0].campaign_budget.resource_name
    old = _micros(rows[0].campaign_budget.amount_micros)
    if rows[0].campaign_budget.explicitly_shared:
        print("⚠️  POZOR: kampaň jede na SDÍLENÉM rozpočtu — změna ovlivní všechny "
              "kampaně, které ho používají.")

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


def cmd_budget_create(args: argparse.Namespace) -> None:
    """Create a SHARED daily budget (one budget for multiple campaigns)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("CampaignBudgetOperation")
    b = op.create
    b.name = args.name
    b.amount_micros = _to_micros(args.amount)
    b.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    b.explicitly_shared = True

    print(f"PLÁN: nový SDÍLENÝ rozpočet '{args.name}' {float(args.amount):,.0f} Kč/den")
    print("      (kampaně připojíš přes `budget-assign`)")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignBudgetService", method_name="mutate_campaign_budgets",
                         request_type="MutateCampaignBudgetsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"sdílený rozpočet '{args.name}'")


def cmd_budget_remove(args: argparse.Namespace) -> None:
    """Remove an (orphan) budget — fails on Google's side while campaigns
    still reference it."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("CampaignBudgetOperation")
    op.remove = client.get_service("CampaignBudgetService").campaign_budget_path(
        cid, args.budget_id)
    print(f"PLÁN: smazat rozpočet {args.budget_id} (jde jen bez připojených kampaní)")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignBudgetService",
                         method_name="mutate_campaign_budgets",
                         request_type="MutateCampaignBudgetsRequest", operations=[op],
                         confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"smazán rozpočet {args.budget_id}")


def cmd_budget_assign(args: argparse.Namespace) -> None:
    """Point campaign(s) at a (shared) budget."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    c_service = client.get_service("CampaignService")
    b_service = client.get_service("CampaignBudgetService")
    budget_rn = b_service.campaign_budget_path(cid, args.budget_id)
    campaign_ids = [c.strip() for c in args.campaigns.split(",") if c.strip()]
    if not campaign_ids:
        _die("Zadej --campaigns id1,id2,…")

    ops = []
    for camp_id in campaign_ids:
        op = client.get_type("CampaignOperation")
        c = op.update
        c.resource_name = c_service.campaign_path(cid, camp_id)
        c.campaign_budget = budget_rn
        client.copy_from(op.update_mask, _field_mask(client, c))
        ops.append(op)

    print(f"PLÁN: kampaně {', '.join(campaign_ids)} → rozpočet {args.budget_id}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignService", method_name="mutate_campaigns",
                         request_type="MutateCampaignsRequest", operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm,
                     f"{len(campaign_ids)} kampaní na rozpočet {args.budget_id}")
