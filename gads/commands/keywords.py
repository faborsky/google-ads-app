"""Keywords & ad-group/campaign negatives."""
from __future__ import annotations

import argparse
import json

from gads.api import _clean_id, _get_client, _run_mutation, _run_query, _show_result
from gads.formatting import _die, _micros, _output_json, _to_micros


def cmd_keywords(args: argparse.Namespace) -> None:
    """List keywords of an ad group / campaign (with criterion IDs for keyword-remove)."""
    client = _get_client(args.account)
    where = "WHERE ad_group_criterion.type = 'KEYWORD' AND ad_group_criterion.status != 'REMOVED' AND ad_group_criterion.negative = FALSE"
    if args.ad_group:
        where += f" AND ad_group.id = {args.ad_group}"
    if args.campaign:
        where += f" AND campaign.id = {args.campaign}"
    gaql = f"""
        SELECT ad_group_criterion.criterion_id, ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type, ad_group_criterion.status,
               ad_group_criterion.cpc_bid_micros, ad_group.id, ad_group.name, campaign.name
        FROM ad_group_criterion
        {where}
        ORDER BY campaign.name, ad_group.name
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = [{
        "criterion": f"{r.ad_group.id}~{r.ad_group_criterion.criterion_id}",
        "text": r.ad_group_criterion.keyword.text,
        "match_type": r.ad_group_criterion.keyword.match_type.name,
        "status": r.ad_group_criterion.status.name,
        "cpc_bid": _micros(r.ad_group_criterion.cpc_bid_micros),
        "ad_group": r.ad_group.name,
        "campaign": r.campaign.name,
    } for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("No keywords found.")
        return
    for k in out:
        print(f"{k['criterion']:>24}  [{k['match_type']:<6}] {k['status']:<8} "
              f"cpc {k['cpc_bid']:>6,.1f}  {k['text']}")


def cmd_keyword_add(args: argparse.Namespace) -> None:
    """Batch-add positive keywords to an ad group from a JSON array.

    JSON: [{"text": "vibe coding kurz", "match_type": "phrase", "cpc": 25}, ...]
    match_type: exact | phrase | broad (default broad)
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    ag_service = client.get_service("AdGroupService")
    try:
        keywords = json.loads(args.keywords_json)
    except json.JSONDecodeError as ex:
        _die(f"Neplatný JSON: {ex}")

    ops = []
    for kw in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        crit = op.create
        crit.ad_group = ag_service.ad_group_path(cid, args.ad_group)
        crit.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        crit.keyword.text = kw["text"]
        crit.keyword.match_type = client.enums.KeywordMatchTypeEnum[
            kw.get("match_type", "broad").upper()
        ]
        if kw.get("cpc"):
            crit.cpc_bid_micros = _to_micros(kw["cpc"])
        ops.append(op)

    print(f"PLÁN: přidat {len(ops)} klíčových slov do ad group {args.ad_group}:")
    for kw in keywords:
        print(f"   [{kw.get('match_type', 'broad'):<6}] {kw['text']}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupCriterionService", method_name="mutate_ad_group_criteria",
                         request_type="MutateAdGroupCriteriaRequest", operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"{len(ops)} klíčových slov")


def cmd_negative_add(args: argparse.Namespace) -> None:
    """Add negative keywords at ad-group OR campaign level."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    match_type = client.enums.KeywordMatchTypeEnum[args.match_type.upper()]
    terms = [t.strip() for t in args.keywords.split(",") if t.strip()]
    if not terms:
        _die("Žádná klíčová slova (--keywords).")

    if args.ad_group:
        ag_service = client.get_service("AdGroupService")
        ops = []
        for t in terms:
            op = client.get_type("AdGroupCriterionOperation")
            crit = op.create
            crit.ad_group = ag_service.ad_group_path(cid, args.ad_group)
            crit.negative = True
            crit.keyword.text = t
            crit.keyword.match_type = match_type
            ops.append(op)
        scope = f"ad group {args.ad_group}"
        svc, method, req = ("AdGroupCriterionService", "mutate_ad_group_criteria",
                            "MutateAdGroupCriteriaRequest")
    elif args.campaign:
        c_service = client.get_service("CampaignService")
        ops = []
        for t in terms:
            op = client.get_type("CampaignCriterionOperation")
            crit = op.create
            crit.campaign = c_service.campaign_path(cid, args.campaign)
            crit.negative = True
            crit.keyword.text = t
            crit.keyword.match_type = match_type
            ops.append(op)
        scope = f"kampaň {args.campaign}"
        svc, method, req = ("CampaignCriterionService", "mutate_campaign_criteria",
                            "MutateCampaignCriteriaRequest")
    else:
        _die("Zadej --ad-group NEBO --campaign.")
        return

    print(f"PLÁN: přidat {len(ops)} negativ ({args.match_type}) na {scope}:")
    for t in terms:
        print(f"   −{t}")
    resp = _run_mutation(client, args.account, cid, service_name=svc, method_name=method,
                         request_type=req, operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"{len(ops)} negativ na {scope}")


def cmd_keyword_remove(args: argparse.Namespace) -> None:
    """Remove ad-group keyword criteria by 'adGroupId~criterionId' fragments."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    frags = [f.strip() for f in args.criteria.split(",") if f.strip()]
    if not frags:
        _die("Zadej --criteria 'adGroupId~criterionId,...'")
    ops = []
    for fr in frags:
        op = client.get_type("AdGroupCriterionOperation")
        op.remove = f"customers/{cid}/adGroupCriteria/{fr}"
        ops.append(op)
    print(f"PLÁN: odebrat {len(ops)} klíčových slov:")
    for fr in frags:
        print(f"   − {fr}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupCriterionService", method_name="mutate_ad_group_criteria",
                         request_type="MutateAdGroupCriteriaRequest", operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"odebráno {len(ops)} klíčových slov")
