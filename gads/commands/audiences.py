"""Audiences / remarketing: user lists, attach to campaign/ad group
(Observation vs Targeting), exclusions.

Notes (verified 2026-07-19, v24):
- Rule-based (site-visitor) lists are created via UserListService; lookalike
  lists are read-only (system-generated) and Customer Match is a separate
  OfflineUserDataJob flow (not wrapped here).
- Positive user-list criteria cannot exist at campaign AND ad-group level of
  the same campaign simultaneously. Campaign-level positive audience targeting
  works on SEARCH only.
- Serving minimum on Search: ~100 active users/30 days.
- Observation (bid_only=true) vs Targeting (bid_only=false) lives on the
  ENTITY's targeting_setting, not on the criterion. Google recommends
  Observation for audiences on Search.
"""
from __future__ import annotations

import argparse

from gads.api import (_clean_id, _field_mask, _get_client, _run_mutation,
                      _run_query, _show_result)
from gads.formatting import _die, _output_json


def cmd_audiences(args: argparse.Namespace) -> None:
    """List user lists (remarketing audiences) with size and eligibility."""
    client = _get_client(args.account)
    gaql = """
        SELECT user_list.id, user_list.name, user_list.type,
               user_list.membership_status, user_list.membership_life_span,
               user_list.size_for_search, user_list.eligible_for_search,
               user_list.description
        FROM user_list
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = [{
        "id": str(r.user_list.id),
        "name": r.user_list.name,
        "type": r.user_list.type_.name,
        "status": r.user_list.membership_status.name,
        "life_span_days": r.user_list.membership_life_span,
        "size_for_search": r.user_list.size_for_search,
        "eligible_for_search": r.user_list.eligible_for_search,
    } for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádné user listy.")
        return
    for u in out:
        eligible = "" if u["eligible_for_search"] else "  ⚠️ NE pro search"
        print(f"{u['id']:>13}  {u['type']:<22} {u['status']:<7} "
              f"search size {u['size_for_search']:>8,}  {u['name']}{eligible}")


def cmd_audience_create(args: argparse.Namespace) -> None:
    """Create a rule-based remarketing list: visitors of URLs containing a string."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("UserListOperation")
    ul = op.create
    ul.name = args.name
    if args.description:
        ul.description = args.description
    ul.membership_status = client.enums.UserListMembershipStatusEnum.OPEN
    ul.membership_life_span = args.membership_days

    rule_item = client.get_type("UserListRuleItemInfo")
    rule_item.name = "url__"
    rule_item.string_rule_item.operator = (
        client.enums.UserListStringRuleItemOperatorEnum.CONTAINS)
    rule_item.string_rule_item.value = args.url_contains

    item_group = client.get_type("UserListRuleItemGroupInfo")
    item_group.rule_items.append(rule_item)
    operand = client.get_type("FlexibleRuleOperandInfo")
    operand.rule.rule_item_groups.append(item_group)

    flexible = ul.rule_based_user_list.flexible_rule_user_list
    flexible.inclusive_rule_operator = client.enums.UserListFlexibleRuleOperatorEnum.AND
    flexible.inclusive_operands.append(operand)
    ul.rule_based_user_list.prepopulation_status = (
        client.enums.UserListPrepopulationStatusEnum.REQUESTED)

    print(f"PLÁN: nový user list '{args.name}' — návštěvníci URL obsahující "
          f"'{args.url_contains}', členství {args.membership_days} dní, "
          f"prepopulace za ~30 dní zpětně")
    resp = _run_mutation(client, args.account, cid,
                         service_name="UserListService", method_name="mutate_user_lists",
                         request_type="MutateUserListsRequest", operations=[op],
                         confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"user list '{args.name}'")
        if args.confirm:
            print("   Pozor: list sbírá návštěvníky přes Google Ads tag — zkontroluj, "
                  "že web tag/remarketing měření běží. Serving minimum na search "
                  "≈ 100 aktivních uživatelů/30 dní.")


def _user_list_names(client, cid, account) -> dict[str, str]:
    rows = _run_query(client, cid,
                      "SELECT user_list.id, user_list.name FROM user_list", account)
    return {str(r.user_list.id): r.user_list.name for r in rows}


def cmd_audiences_attached(args: argparse.Namespace) -> None:
    """What audiences are attached where (campaign + ad-group level, incl.
    exclusions and the entity's Observation/Targeting mode)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    names = _user_list_names(client, cid, args.account)
    out = []

    where = "WHERE campaign_criterion.type = 'USER_LIST' AND campaign_criterion.status != 'REMOVED'"
    if args.campaign:
        where += f" AND campaign.id = {args.campaign}"
    for r in _run_query(client, cid, f"""
        SELECT campaign.id, campaign.name, campaign_criterion.criterion_id,
               campaign_criterion.negative, campaign_criterion.user_list.user_list
        FROM campaign_criterion {where}
    """, args.account):
        list_id = r.campaign_criterion.user_list.user_list.split("/")[-1]
        out.append({
            "level": "campaign",
            "campaign_id": str(r.campaign.id), "campaign": r.campaign.name,
            "criterion_id": str(r.campaign_criterion.criterion_id),
            "list_id": list_id, "list_name": names.get(list_id, "?"),
            "negative": r.campaign_criterion.negative,
        })

    where = "WHERE ad_group_criterion.type = 'USER_LIST' AND ad_group_criterion.status != 'REMOVED'"
    if args.campaign:
        where += f" AND campaign.id = {args.campaign}"
    for r in _run_query(client, cid, f"""
        SELECT campaign.name, ad_group.id, ad_group.name,
               ad_group_criterion.criterion_id, ad_group_criterion.negative,
               ad_group_criterion.user_list.user_list
        FROM ad_group_criterion {where}
    """, args.account):
        list_id = r.ad_group_criterion.user_list.user_list.split("/")[-1]
        out.append({
            "level": "ad_group",
            "campaign": r.campaign.name,
            "ad_group_id": str(r.ad_group.id), "ad_group": r.ad_group.name,
            "criterion_id": str(r.ad_group_criterion.criterion_id),
            "list_id": list_id, "list_name": names.get(list_id, "?"),
            "negative": r.ad_group_criterion.negative,
        })
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádná publika napojená na kampaně/sestavy.")
        return
    for a in out:
        target = a.get("ad_group") or a.get("campaign")
        neg = "EXCLUDED " if a["negative"] else ""
        print(f"crit {a['criterion_id']:>12}  {a['level']:<9} {neg}{a['list_name']:<32} → {target}")


def _set_audience_mode(client, cid, account, *, campaign_id=None, ad_group_id=None,
                       observation: bool, confirm: bool) -> None:
    """Flip the AUDIENCE target restriction (Observation=bid_only vs Targeting)
    on a campaign or ad group. Reads current restrictions and resubmits the
    full list (the API replaces the whole targeting_setting)."""
    if campaign_id:
        resource, id_field, svc, op_type, req, method = (
            "campaign", campaign_id, "CampaignService", "CampaignOperation",
            "MutateCampaignsRequest", "mutate_campaigns")
        rn = client.get_service("CampaignService").campaign_path(cid, campaign_id)
        gaql = (f"SELECT campaign.targeting_setting.target_restrictions "
                f"FROM campaign WHERE campaign.id = {campaign_id}")
    else:
        resource, id_field, svc, op_type, req, method = (
            "ad_group", ad_group_id, "AdGroupService", "AdGroupOperation",
            "MutateAdGroupsRequest", "mutate_ad_groups")
        rn = client.get_service("AdGroupService").ad_group_path(cid, ad_group_id)
        gaql = (f"SELECT ad_group.targeting_setting.target_restrictions "
                f"FROM ad_group WHERE ad_group.id = {ad_group_id}")

    rows = _run_query(client, cid, gaql, account)
    if not rows:
        _die(f"{resource} {id_field} nenalezen.")
    restrictions = list(getattr(rows[0], resource).targeting_setting.target_restrictions)

    op = client.get_type(op_type)
    entity = op.update
    entity.resource_name = rn
    found = False
    for tr in restrictions:
        new_tr = client.get_type("TargetRestriction")
        client.copy_from(new_tr, tr)
        if tr.targeting_dimension.name == "AUDIENCE":
            new_tr.bid_only = observation
            found = True
        entity.targeting_setting.target_restrictions.append(new_tr)
    if not found:
        new_tr = client.get_type("TargetRestriction")
        new_tr.targeting_dimension = client.enums.TargetingDimensionEnum.AUDIENCE
        new_tr.bid_only = observation
        entity.targeting_setting.target_restrictions.append(new_tr)
    client.copy_from(op.update_mask, _field_mask(client, entity))

    mode = "OBSERVATION (bid_only)" if observation else "TARGETING (zúží zobrazování!)"
    print(f"   + režim publik na {resource} {id_field}: {mode}")
    _run_mutation(client, account, cid, service_name=svc, method_name=method,
                  request_type=req, operations=[op], confirm=confirm)


def cmd_audience_attach(args: argparse.Namespace) -> None:
    """Attach a user list to a campaign or ad group (positive criterion) and
    optionally set the entity's Observation/Targeting mode."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    if bool(args.campaign) == bool(args.ad_group):
        _die("Zadej --campaign NEBO --ad-group.")
    ul_rn = f"customers/{cid}/userLists/{args.list}"

    if args.campaign:
        op = client.get_type("CampaignCriterionOperation")
        crit = op.create
        crit.campaign = client.get_service("CampaignService").campaign_path(cid, args.campaign)
        svc, method, req = ("CampaignCriterionService", "mutate_campaign_criteria",
                            "MutateCampaignCriteriaRequest")
        scope = f"kampaň {args.campaign}"
    else:
        op = client.get_type("AdGroupCriterionOperation")
        crit = op.create
        crit.ad_group = client.get_service("AdGroupService").ad_group_path(cid, args.ad_group)
        svc, method, req = ("AdGroupCriterionService", "mutate_ad_group_criteria",
                            "MutateAdGroupCriteriaRequest")
        scope = f"ad group {args.ad_group}"
    crit.user_list.user_list = ul_rn
    if args.bid_modifier:
        crit.bid_modifier = float(args.bid_modifier)

    mode_note = f", režim {args.mode}" if args.mode else ""
    print(f"PLÁN: napojit user list {args.list} na {scope}{mode_note}")
    resp = _run_mutation(client, args.account, cid, service_name=svc,
                         method_name=method, request_type=req,
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"publikum {args.list} → {scope}")
    if args.mode:
        _set_audience_mode(client, cid, args.account,
                           campaign_id=args.campaign, ad_group_id=args.ad_group,
                           observation=(args.mode == "observation"),
                           confirm=args.confirm)


def cmd_audience_exclude(args: argparse.Namespace) -> None:
    """Exclude a user list from a campaign (e.g. existing customers from
    acquisition). Campaign-level negative criterion."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("CampaignCriterionOperation")
    crit = op.create
    crit.campaign = client.get_service("CampaignService").campaign_path(cid, args.campaign)
    crit.negative = True
    crit.user_list.user_list = f"customers/{cid}/userLists/{args.list}"

    print(f"PLÁN: VYLOUČIT user list {args.list} z kampaně {args.campaign}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignCriterionService",
                         method_name="mutate_campaign_criteria",
                         request_type="MutateCampaignCriteriaRequest",
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm,
                     f"vyloučení publika {args.list} z kampaně {args.campaign}")


def cmd_audience_detach(args: argparse.Namespace) -> None:
    """Detach an audience criterion (criterion IDs from audiences-attached)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    if bool(args.campaign) == bool(args.ad_group):
        _die("Zadej --campaign NEBO --ad-group (odkud kritérium odebrat).")
    if args.campaign:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = f"customers/{cid}/campaignCriteria/{args.campaign}~{args.criterion}"
        svc, method, req = ("CampaignCriterionService", "mutate_campaign_criteria",
                            "MutateCampaignCriteriaRequest")
        scope = f"kampaň {args.campaign}"
    else:
        op = client.get_type("AdGroupCriterionOperation")
        op.remove = f"customers/{cid}/adGroupCriteria/{args.ad_group}~{args.criterion}"
        svc, method, req = ("AdGroupCriterionService", "mutate_ad_group_criteria",
                            "MutateAdGroupCriteriaRequest")
        scope = f"ad group {args.ad_group}"

    print(f"PLÁN: odpojit audience criterion {args.criterion} z {scope}")
    resp = _run_mutation(client, args.account, cid, service_name=svc,
                         method_name=method, request_type=req,
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"odpojeno criterion {args.criterion}")
