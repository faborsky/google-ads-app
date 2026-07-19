"""Ad groups: list, create."""
from __future__ import annotations

import argparse

from gads.api import _clean_id, _get_client, _run_mutation, _run_query, _show_result
from gads.formatting import _micros, _output_json, _to_micros


def cmd_ad_groups(args: argparse.Namespace) -> None:
    """List ad groups (optionally within one campaign)."""
    client = _get_client(args.account)
    where = "WHERE ad_group.status != 'REMOVED'"
    if args.campaign:
        where += f" AND campaign.id = {args.campaign}"
    gaql = f"""
        SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.type,
               ad_group.cpc_bid_micros, campaign.id, campaign.name
        FROM ad_group
        {where}
        ORDER BY campaign.name, ad_group.name
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = [{
        "id": str(r.ad_group.id),
        "name": r.ad_group.name,
        "status": r.ad_group.status.name,
        "type": r.ad_group.type_.name,
        "cpc_bid": _micros(r.ad_group.cpc_bid_micros),
        "campaign_id": str(r.campaign.id),
        "campaign": r.campaign.name,
    } for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("No ad groups found.")
        return
    for g in out:
        print(f"{g['id']:>12}  {g['status']:<8}  cpc {g['cpc_bid']:>7,.1f}  "
              f"{g['type']:<22}  {g['campaign'][:24]:<24}  {g['name']}")


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
