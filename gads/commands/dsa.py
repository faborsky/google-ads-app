"""Dynamic Search Ads: campaign DSA setting, DSA ad group + ad, webpage
targeting criteria.

Constraints (v24): DSA ad group type = SEARCH_DYNAMIC_ADS (immutable), only in
campaigns with a valid dynamic_search_ads_setting; NO positive keywords and NO
RSAs in a DSA ad group; the ad's headline/display URL/final URL are generated
by Google at serve time — you supply only description(s). Always pair DSA with
negatives (webpage negatives or keyword negatives).
"""
from __future__ import annotations

import argparse

from gads.api import (_clean_id, _field_mask, _get_client, _run_mutation,
                      _run_query, _show_result)
from gads.formatting import _die, _output_json, _to_micros

_OPERANDS = {"url": "URL", "title": "PAGE_TITLE", "content": "PAGE_CONTENT",
             "category": "CATEGORY", "label": "CUSTOM_LABEL"}


def cmd_dsa_setting(args: argparse.Namespace) -> None:
    """Set a campaign's DSA setting (domain + language) — turns a SEARCH
    campaign into a DSA-capable one."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    service = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    c = op.update
    c.resource_name = service.campaign_path(cid, args.campaign_id)
    c.dynamic_search_ads_setting.domain_name = args.domain
    c.dynamic_search_ads_setting.language_code = args.language_code
    if args.supplied_urls_only:
        c.dynamic_search_ads_setting.use_supplied_urls_only = True
    client.copy_from(op.update_mask, _field_mask(client, c))

    print(f"PLÁN: kampaň {args.campaign_id} → DSA setting: doména {args.domain}, "
          f"jazyk {args.language_code}"
          + (", jen dodané URL (page feed)" if args.supplied_urls_only else ""))
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignService", method_name="mutate_campaigns",
                         request_type="MutateCampaignsRequest", operations=[op],
                         confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"DSA setting kampaně {args.campaign_id}")


def cmd_dsa_ad_group_create(args: argparse.Namespace) -> None:
    """Create a DSA ad group (type SEARCH_DYNAMIC_ADS) in a DSA-enabled campaign."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("AdGroupOperation")
    ag = op.create
    ag.name = args.name
    ag.campaign = client.get_service("CampaignService").campaign_path(cid, args.campaign)
    ag.status = client.enums.AdGroupStatusEnum.ENABLED
    ag.type_ = client.enums.AdGroupTypeEnum.SEARCH_DYNAMIC_ADS
    if args.cpc:
        ag.cpc_bid_micros = _to_micros(args.cpc)

    print(f"PLÁN: nová DSA ad group '{args.name}' v kampani {args.campaign}"
          + (f", CPC {float(args.cpc):,.0f} Kč" if args.cpc else "")
          + " (kampaň musí mít dsa-setting!)")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupService", method_name="mutate_ad_groups",
                         request_type="MutateAdGroupsRequest", operations=[op],
                         confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"DSA ad group '{args.name}'")


def cmd_dsa_create(args: argparse.Namespace) -> None:
    """Create an Expanded DSA ad (descriptions only — headline/URL generated)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    descriptions = [d.strip() for d in args.descriptions.split("|") if d.strip()]
    if not 1 <= len(descriptions) <= 2:
        _die(f"DSA ad má 1–2 descriptions (máš {len(descriptions)}).")
    too_long = [d for d in descriptions if len(d) > 90]
    if too_long:
        _die(f"Description max 90 znaků, překračují: {too_long}")

    op = client.get_type("AdGroupAdOperation")
    aga = op.create
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad_group = client.get_service("AdGroupService").ad_group_path(cid, args.ad_group)
    aga.ad.expanded_dynamic_search_ad.description = descriptions[0]
    if len(descriptions) > 1:
        aga.ad.expanded_dynamic_search_ad.description2 = descriptions[1]

    print(f"PLÁN: nový DSA inzerát v ad group {args.ad_group} "
          f"({len(descriptions)} descriptions; headline+URL generuje Google)")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupAdService", method_name="mutate_ad_group_ads",
                         request_type="MutateAdGroupAdsRequest", operations=[op],
                         confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, "DSA inzerát")


def cmd_webpage_targets(args: argparse.Namespace) -> None:
    """List webpage targeting criteria of a DSA ad group."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rows = _run_query(client, cid, f"""
        SELECT ad_group_criterion.criterion_id, ad_group_criterion.negative,
               ad_group_criterion.webpage.criterion_name,
               ad_group_criterion.webpage.conditions,
               ad_group.id, ad_group.name
        FROM ad_group_criterion
        WHERE ad_group_criterion.type = 'WEBPAGE'
          AND ad_group_criterion.status != 'REMOVED'
          AND ad_group.id = {args.ad_group}
    """, args.account)
    out = []
    for r in rows:
        agc = r.ad_group_criterion
        out.append({
            "criterion": f"{r.ad_group.id}~{agc.criterion_id}",
            "name": agc.webpage.criterion_name,
            "negative": agc.negative,
            "conditions": [
                {"operand": c.operand.name, "argument": c.argument}
                for c in agc.webpage.conditions],
        })
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádná webpage kritéria — DSA skupina bez podmínek cílí na CELÝ web z dsa-setting.")
        return
    for w in out:
        neg = "EXCLUDE " if w["negative"] else ""
        conds = " AND ".join(f"{c['operand']}~'{c['argument']}'" for c in w["conditions"]) or "ALL_PAGES"
        print(f"{w['criterion']:>24}  {neg}{w['name'] or '-'}: {conds}")


def cmd_webpage_target_add(args: argparse.Namespace) -> None:
    """Add a webpage targeting criterion (or exclusion) to a DSA ad group.

    --conditions 'url:blog,title:kurz' — operands: url, title, content,
    category, label (1–3 conditions, ANDed). Omit = target all pages.
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("AdGroupCriterionOperation")
    crit = op.create
    crit.ad_group = client.get_service("AdGroupService").ad_group_path(cid, args.ad_group)
    if args.negative:
        crit.negative = True
    crit.webpage.criterion_name = args.name
    conditions = [c.strip() for c in (args.conditions or "").split(",") if c.strip()]
    if len(conditions) > 3:
        _die("Max 3 podmínky (ANDují se).")
    for cond in conditions:
        try:
            operand, argument = cond.split(":", 1)
        except ValueError:
            _die(f"Podmínku čekám jako 'operand:hodnota', dostal jsem '{cond}'.")
        if operand not in _OPERANDS:
            _die(f"Neznámý operand '{operand}' — použij {', '.join(_OPERANDS)}.")
        ci = client.get_type("WebpageConditionInfo")
        ci.operand = client.enums.WebpageConditionOperandEnum[_OPERANDS[operand]]
        ci.argument = argument
        crit.webpage.conditions.append(ci)
    if args.cpc and not args.negative:
        crit.cpc_bid_micros = _to_micros(args.cpc)

    verb = "VYLOUČIT" if args.negative else "cílit"
    print(f"PLÁN: DSA ad group {args.ad_group} — {verb} '{args.name}': "
          f"{args.conditions or 'všechny stránky'}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupCriterionService",
                         method_name="mutate_ad_group_criteria",
                         request_type="MutateAdGroupCriteriaRequest",
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"webpage criterion '{args.name}'")


def cmd_webpage_target_remove(args: argparse.Namespace) -> None:
    """Remove webpage criteria ('adGroupId~criterionId' from webpage-targets)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    frags = [f.strip() for f in args.criteria.split(",") if f.strip()]
    if not frags:
        _die("Zadej --criteria 'adGroupId~criterionId,…'")
    ops = []
    for fr in frags:
        op = client.get_type("AdGroupCriterionOperation")
        op.remove = f"customers/{cid}/adGroupCriteria/{fr}"
        ops.append(op)
    print(f"PLÁN: odebrat {len(ops)} webpage kritérií")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupCriterionService",
                         method_name="mutate_ad_group_criteria",
                         request_type="MutateAdGroupCriteriaRequest",
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"odebráno {len(ops)} webpage kritérií")
