"""Campaigns: list, create, status, bidding."""
from __future__ import annotations

import argparse

from gads.api import (_clean_id, _execute_with_retry, _field_mask, _get_client,
                      _quota_guard, _require_paused_before_remove,
                      _run_mutation, _run_query, _show_result, _track_ops)
from gads.formatting import _die, _micros, _output_json, _to_micros


def cmd_campaigns(args: argparse.Namespace) -> None:
    """List search campaigns for a customer."""
    client = _get_client(args.account)
    where = "WHERE campaign.advertising_channel_type = 'SEARCH'"
    if args.status:
        where += f" AND campaign.status = '{args.status.upper()}'"
    else:
        where += " AND campaign.status != 'REMOVED'"
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


def cmd_campaign_status(args: argparse.Namespace) -> None:
    """Enable / pause / remove a campaign. REMOVED is permanent → requires the
    campaign to be PAUSED first (see _require_paused_before_remove)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    if args.status == "removed":
        _require_paused_before_remove(
            client, args.account, cid,
            gaql=f"SELECT campaign.status FROM campaign WHERE campaign.id = {args.campaign_id}",
            entity_label=f"kampaň {args.campaign_id}", force=args.force)
        # REMOVED cannot be set via a status update ("Enum value 'REMOVED'
        # cannot be used", verified live) — it requires a remove operation.
        op.remove = service.campaign_path(cid, args.campaign_id)
    else:
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
    """Create a SEARCH campaign + budget atomically (starts PAUSED), including
    geo + language targeting (defaults: Czech Republic + Czech)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    budget_service = client.get_service("CampaignBudgetService")
    campaign_service = client.get_service("CampaignService")
    gads_service = client.get_service("GoogleAdsService")
    budget_rn = budget_service.campaign_budget_path(cid, "-1")   # temp id
    campaign_rn = campaign_service.campaign_path(cid, "-2")      # temp id

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
    c.resource_name = campaign_rn
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

    geo_ids = [g.strip() for g in (args.geo or "").split(",") if g.strip()]
    lang_ids = [l.strip() for l in (args.language or "").split(",") if l.strip()]
    for gid in geo_ids:
        mo = client.get_type("MutateOperation")
        cc = mo.campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.location.geo_target_constant = gads_service.geo_target_constant_path(gid)
        ops.append(mo)
    for lid in lang_ids:
        mo = client.get_type("MutateOperation")
        cc = mo.campaign_criterion_operation.create
        cc.campaign = campaign_rn
        cc.language.language_constant = gads_service.language_constant_path(lid)
        ops.append(mo)

    label = _apply_bidding(client, client.get_type("Campaign"), args.bidding, args.target_cpa, args.target_roas)
    print(f"PLÁN: nová SEARCH kampaň '{args.name}' (PAUSED), "
          f"rozpočet {float(args.budget):,.0f} Kč/den, bidding {label}")
    print(f"      geo: {', '.join(geo_ids) or '— (celý svět!)'}  "
          f"jazyk: {', '.join(lang_ids) or '— (všechny!)'}")

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
            for field in ("campaign_result", "campaign_budget_result", "campaign_criterion_result"):
                if r._pb.HasField(field):
                    print(f"   {getattr(r, field).resource_name}")
    else:
        print("\n✅ VALIDACE OK — kampaň + rozpočet + cílení. (dry-run: nic nezapsáno) — přidej --confirm.")
