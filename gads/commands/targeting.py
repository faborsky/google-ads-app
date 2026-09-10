"""Campaign targeting: geo (incl. proximity + exclusions), language, ad
schedule, device bid modifiers; ad-group demographics (age/gender/income).

Criteria are IMMUTABLE (except bid_modifier) — changing targeting = remove the
old criterion + create a new one. Criterion IDs come from `campaign-targeting`.
"""
from __future__ import annotations

import argparse
import json

from gads.api import (_clean_id, _execute_with_retry, _field_mask, _get_client,
                      _quota_guard, _run_mutation, _run_query, _show_result,
                      _track_ops)
from gads.formatting import _die, _output_json

_DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
_DEVICES = ["MOBILE", "DESKTOP", "TABLET", "CONNECTED_TV", "OTHER"]

_AGE_RANGES = ["AGE_RANGE_18_24", "AGE_RANGE_25_34", "AGE_RANGE_35_44",
               "AGE_RANGE_45_54", "AGE_RANGE_55_64", "AGE_RANGE_65_UP",
               "AGE_RANGE_UNDETERMINED"]
_GENDERS = ["MALE", "FEMALE", "UNDETERMINED"]
_INCOMES = ["INCOME_RANGE_0_50", "INCOME_RANGE_50_60", "INCOME_RANGE_60_70",
            "INCOME_RANGE_70_80", "INCOME_RANGE_80_90", "INCOME_RANGE_90_UP",
            "INCOME_RANGE_UNDETERMINED"]


def cmd_geo_suggest(args: argparse.Namespace) -> None:
    """Look up geo target constant IDs by location name (for geo-target/--geo)."""
    client = _get_client(args.account)
    svc = client.get_service("GeoTargetConstantService")
    request = client.get_type("SuggestGeoTargetConstantsRequest")
    request.locale = args.locale
    if args.country:
        request.country_code = args.country
    names = [n.strip() for n in args.name.split(",") if n.strip()]
    request.location_names.names.extend(names)

    _quota_guard(args.account, 1)
    resp = _execute_with_retry(
        lambda: svc.suggest_geo_target_constants(request=request),
        what="geo-suggest")
    if resp is None:
        return
    _track_ops(args.account, 1)

    out = []
    for s in resp.geo_target_constant_suggestions:
        g = s.geo_target_constant
        out.append({
            "id": str(g.id),
            "name": g.name,
            "canonical_name": g.canonical_name,
            "country_code": g.country_code,
            "target_type": g.target_type,
            "reach": s.reach,
            "search_term": s.search_term,
        })
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Nic nenalezeno.")
        return
    for g in out:
        print(f"{g['id']:>10}  {g['target_type']:<12} reach {g['reach']:>10,}  {g['canonical_name']}")


def cmd_campaign_targeting(args: argparse.Namespace) -> None:
    """List a campaign's targeting criteria (geo/language/schedule/device/proximity)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    gaql = f"""
        SELECT campaign_criterion.criterion_id, campaign_criterion.type,
               campaign_criterion.negative, campaign_criterion.bid_modifier,
               campaign_criterion.location.geo_target_constant,
               campaign_criterion.language.language_constant,
               campaign_criterion.device.type,
               campaign_criterion.ad_schedule.day_of_week,
               campaign_criterion.ad_schedule.start_hour,
               campaign_criterion.ad_schedule.end_hour,
               campaign_criterion.proximity.radius,
               campaign_criterion.proximity.radius_units,
               campaign_criterion.proximity.geo_point.latitude_in_micro_degrees,
               campaign_criterion.proximity.geo_point.longitude_in_micro_degrees
        FROM campaign_criterion
        WHERE campaign.id = {args.campaign_id}
          AND campaign_criterion.type IN ('LOCATION', 'LANGUAGE', 'AD_SCHEDULE',
                                          'DEVICE', 'PROXIMITY')
          AND campaign_criterion.status != 'REMOVED'
    """
    rows = _run_query(client, cid, gaql, args.account)
    out = []
    for r in rows:
        cc = r.campaign_criterion
        item = {
            "criterion_id": str(cc.criterion_id),
            "type": cc.type_.name,
            "negative": cc.negative,
            "bid_modifier": round(cc.bid_modifier, 2) if cc.bid_modifier else None,
        }
        if cc.type_.name == "LOCATION":
            item["geo_target_constant"] = cc.location.geo_target_constant
        elif cc.type_.name == "LANGUAGE":
            item["language_constant"] = cc.language.language_constant
        elif cc.type_.name == "DEVICE":
            item["device"] = cc.device.type_.name
        elif cc.type_.name == "AD_SCHEDULE":
            item["schedule"] = (f"{cc.ad_schedule.day_of_week.name} "
                                f"{cc.ad_schedule.start_hour}–{cc.ad_schedule.end_hour}")
        elif cc.type_.name == "PROXIMITY":
            item["proximity"] = (f"{cc.proximity.geo_point.latitude_in_micro_degrees / 1e6:.4f},"
                                 f"{cc.proximity.geo_point.longitude_in_micro_degrees / 1e6:.4f} "
                                 f"r={cc.proximity.radius} {cc.proximity.radius_units.name}")
        out.append(item)
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Kampaň nemá žádná cílicí kritéria (LOCATION/LANGUAGE/AD_SCHEDULE/DEVICE) "
              "— běží na celý svět, všechny jazyky!")
        return
    for i in out:
        detail = (i.get("geo_target_constant") or i.get("language_constant")
                  or i.get("device") or i.get("schedule") or i.get("proximity") or "")
        neg = " NEGATIVE" if i["negative"] else ""
        bm = f"  bid ×{i['bid_modifier']}" if i["bid_modifier"] else ""
        print(f"{i['criterion_id']:>12}  {i['type']:<12}{neg}{bm}  {detail}")


def cmd_geo_target(args: argparse.Namespace) -> None:
    """Add/exclude/remove campaign geo targeting (geo IDs from geo-suggest),
    incl. proximity (radius) targeting."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    c_service = client.get_service("CampaignService")
    gads_service = client.get_service("GoogleAdsService")
    campaign_rn = c_service.campaign_path(cid, args.campaign_id)

    ops, plan = [], []
    for gid in [g.strip() for g in (args.geo or "").split(",") if g.strip()]:
        op = client.get_type("CampaignCriterionOperation")
        cc = op.create
        cc.campaign = campaign_rn
        cc.location.geo_target_constant = gads_service.geo_target_constant_path(gid)
        if args.negative:
            cc.negative = True
        ops.append(op)
        plan.append(f"{'−' if args.negative else '+'} geo {gid}")
    if args.proximity:
        try:
            lat, lng, km = (p.strip() for p in args.proximity.split(","))
            op = client.get_type("CampaignCriterionOperation")
            cc = op.create
            cc.campaign = campaign_rn
            cc.proximity.geo_point.latitude_in_micro_degrees = int(float(lat) * 1e6)
            cc.proximity.geo_point.longitude_in_micro_degrees = int(float(lng) * 1e6)
            cc.proximity.radius = float(km)
            cc.proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.KILOMETERS
            ops.append(op)
            plan.append(f"+ proximity {lat},{lng} r={km} km")
        except ValueError:
            _die("--proximity čekám jako 'lat,lng,km' (např. '50.08,14.43,20').")
    for crit_id in [c.strip() for c in (args.remove or "").split(",") if c.strip()]:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = f"customers/{cid}/campaignCriteria/{args.campaign_id}~{crit_id}"
        ops.append(op)
        plan.append(f"× remove criterion {crit_id}")
    if not ops:
        _die("Zadej --geo, --proximity a/nebo --remove.")

    print(f"PLÁN: kampaň {args.campaign_id} geo cílení:")
    for p in plan:
        print(f"   {p}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignCriterionService",
                         method_name="mutate_campaign_criteria",
                         request_type="MutateCampaignCriteriaRequest",
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"geo cílení kampaně {args.campaign_id}")


def cmd_language_target(args: argparse.Namespace) -> None:
    """Add/remove campaign language targeting (positive only — API has no
    language exclusion). Czech = 1021, Slovak = 1034, English = 1000."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    c_service = client.get_service("CampaignService")
    gads_service = client.get_service("GoogleAdsService")
    campaign_rn = c_service.campaign_path(cid, args.campaign_id)

    ops, plan = [], []
    for lid in [lang.strip() for lang in (args.language or "").split(",") if lang.strip()]:
        op = client.get_type("CampaignCriterionOperation")
        cc = op.create
        cc.campaign = campaign_rn
        cc.language.language_constant = gads_service.language_constant_path(lid)
        ops.append(op)
        plan.append(f"+ language {lid}")
    for crit_id in [c.strip() for c in (args.remove or "").split(",") if c.strip()]:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = f"customers/{cid}/campaignCriteria/{args.campaign_id}~{crit_id}"
        ops.append(op)
        plan.append(f"× remove criterion {crit_id}")
    if not ops:
        _die("Zadej --language a/nebo --remove.")

    print(f"PLÁN: kampaň {args.campaign_id} jazyky:")
    for p in plan:
        print(f"   {p}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignCriterionService",
                         method_name="mutate_campaign_criteria",
                         request_type="MutateCampaignCriteriaRequest",
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"jazyky kampaně {args.campaign_id}")


def cmd_schedule_set(args: argparse.Namespace) -> None:
    """REPLACE a campaign's ad schedule with the given JSON.

    JSON: [{"day":"MONDAY","start":8,"end":20,"bid_modifier":1.1}, …]
    day: MONDAY…SUNDAY; start/end: whole hours 0–24 (max 6 blocks per day).
    Existing AD_SCHEDULE criteria are removed and the new set created in ONE
    atomic request. Empty list [] = clear the schedule (run 24/7).
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    try:
        schedule = json.loads(args.schedule_json)
    except json.JSONDecodeError as ex:
        _die(f"Neplatný JSON: {ex}")

    existing = _run_query(client, cid, f"""
        SELECT campaign_criterion.criterion_id FROM campaign_criterion
        WHERE campaign.id = {args.campaign_id}
          AND campaign_criterion.type = 'AD_SCHEDULE'
          AND campaign_criterion.status != 'REMOVED'
    """, args.account)

    c_service = client.get_service("CampaignService")
    campaign_rn = c_service.campaign_path(cid, args.campaign_id)
    ops = []
    for r in existing:
        op = client.get_type("CampaignCriterionOperation")
        op.remove = (f"customers/{cid}/campaignCriteria/"
                     f"{args.campaign_id}~{r.campaign_criterion.criterion_id}")
        ops.append(op)
    for block in schedule:
        day = str(block.get("day", "")).upper()
        if day not in _DAYS:
            _die(f"Neznámý den '{block.get('day')}' — použij {', '.join(_DAYS)}.")
        op = client.get_type("CampaignCriterionOperation")
        cc = op.create
        cc.campaign = campaign_rn
        cc.ad_schedule.day_of_week = client.enums.DayOfWeekEnum[day]
        cc.ad_schedule.start_hour = int(block.get("start", 0))
        cc.ad_schedule.end_hour = int(block.get("end", 24))
        cc.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
        cc.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO
        if block.get("bid_modifier"):
            cc.bid_modifier = float(block["bid_modifier"])
        ops.append(op)

    print(f"PLÁN: kampaň {args.campaign_id} — nahradit rozvrh: "
          f"odebrat {len(existing)} bloků, přidat {len(schedule)}:")
    for b in schedule:
        bm = f" ×{b['bid_modifier']}" if b.get("bid_modifier") else ""
        print(f"   {b['day']} {b.get('start', 0)}–{b.get('end', 24)}{bm}")
    if not schedule:
        print("   (prázdný rozvrh = kampaň poběží 24/7)")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignCriterionService",
                         method_name="mutate_campaign_criteria",
                         request_type="MutateCampaignCriteriaRequest",
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"rozvrh kampaně {args.campaign_id}")


def cmd_device_bid(args: argparse.Namespace) -> None:
    """Set a device bid modifier on a campaign. 1.0 = neutral, 0.8 = −20 %,
    0 = don't serve on that device. Range 0.1–10.0 (or exactly 0)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    device = args.device.upper()
    if device not in _DEVICES:
        _die(f"Neznámé zařízení '{args.device}' — použij {', '.join(_DEVICES)}.")
    mod = float(args.modifier)
    if mod != 0 and not (0.1 <= mod <= 10.0):
        _die("Modifier musí být 0 (vypnout zařízení) nebo 0.1–10.0.")

    existing = _run_query(client, cid, f"""
        SELECT campaign_criterion.criterion_id, campaign_criterion.device.type
        FROM campaign_criterion
        WHERE campaign.id = {args.campaign_id}
          AND campaign_criterion.type = 'DEVICE'
          AND campaign_criterion.status != 'REMOVED'
    """, args.account)
    current = {r.campaign_criterion.device.type_.name: r.campaign_criterion.criterion_id
               for r in existing}

    c_service = client.get_service("CampaignService")
    op = client.get_type("CampaignCriterionOperation")
    if device in current:
        cc = op.update
        cc.resource_name = (f"customers/{cid}/campaignCriteria/"
                            f"{args.campaign_id}~{current[device]}")
        cc.bid_modifier = mod
        client.copy_from(op.update_mask, _field_mask(client, cc))
        verb = "update"
    else:
        cc = op.create
        cc.campaign = c_service.campaign_path(cid, args.campaign_id)
        cc.device.type_ = client.enums.DeviceEnum[device]
        cc.bid_modifier = mod
        verb = "create"

    label = "vypnout (nezobrazovat)" if mod == 0 else f"bid ×{mod}"
    print(f"PLÁN: kampaň {args.campaign_id} — {device}: {label} ({verb})")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignCriterionService",
                         method_name="mutate_campaign_criteria",
                         request_type="MutateCampaignCriteriaRequest",
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"{device} {label}")


def cmd_demographics(args: argparse.Namespace) -> None:
    """List ad-group demographic criteria (age/gender/income) incl. exclusions."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    where = ("WHERE ad_group_criterion.type IN ('AGE_RANGE', 'GENDER', 'INCOME_RANGE') "
             "AND ad_group_criterion.status != 'REMOVED'")
    if args.ad_group:
        where += f" AND ad_group.id = {args.ad_group}"
    gaql = f"""
        SELECT ad_group_criterion.criterion_id, ad_group_criterion.type,
               ad_group_criterion.negative, ad_group_criterion.bid_modifier,
               ad_group_criterion.age_range.type, ad_group_criterion.gender.type,
               ad_group_criterion.income_range.type,
               ad_group.id, ad_group.name, campaign.name
        FROM ad_group_criterion
        {where}
    """
    rows = _run_query(client, cid, gaql, args.account)
    out = []
    for r in rows:
        agc = r.ad_group_criterion
        value = (agc.age_range.type_.name if agc.type_.name == "AGE_RANGE"
                 else agc.gender.type_.name if agc.type_.name == "GENDER"
                 else agc.income_range.type_.name)
        out.append({
            "criterion": f"{r.ad_group.id}~{agc.criterion_id}",
            "ad_group": r.ad_group.name,
            "campaign": r.campaign.name,
            "type": agc.type_.name,
            "value": value,
            "negative": agc.negative,
            "bid_modifier": round(agc.bid_modifier, 2) if agc.bid_modifier else None,
        })
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádná demografická kritéria (výchozí = cílí na všechny).")
        return
    for i in out:
        neg = " EXCLUDED" if i["negative"] else ""
        bm = f"  bid ×{i['bid_modifier']}" if i["bid_modifier"] else ""
        print(f"{i['criterion']:>24}  {i['type']:<13} {i['value']:<26}{neg}{bm}  {i['ad_group']}")


def cmd_demographic_target(args: argparse.Namespace) -> None:
    """Add / exclude / remove ad-group demographic criteria.

    --value: age AGE_RANGE_18_24…AGE_RANGE_65_UP | gender MALE/FEMALE/UNDETERMINED
    | income INCOME_RANGE_0_50…INCOME_RANGE_90_UP. --negative = exclusion.
    --remove takes criterion IDs from `demographics`.
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    ag_service = client.get_service("AdGroupService")

    ops, plan = [], []
    for value in [v.strip().upper() for v in (args.value or "").split(",") if v.strip()]:
        op = client.get_type("AdGroupCriterionOperation")
        crit = op.create
        crit.ad_group = ag_service.ad_group_path(cid, args.ad_group)
        if value in _AGE_RANGES:
            crit.age_range.type_ = client.enums.AgeRangeTypeEnum[value]
        elif value in _GENDERS:
            crit.gender.type_ = client.enums.GenderTypeEnum[value]
        elif value in _INCOMES:
            crit.income_range.type_ = client.enums.IncomeRangeTypeEnum[value]
        else:
            _die(f"Neznámá hodnota '{value}'. Age: {', '.join(_AGE_RANGES)}; "
                 f"gender: {', '.join(_GENDERS)}; income: {', '.join(_INCOMES)}.")
        if args.negative:
            crit.negative = True
        if args.modifier and not args.negative:
            crit.bid_modifier = float(args.modifier)
        ops.append(op)
        plan.append(f"{'−' if args.negative else '+'} {value}")
    for crit_id in [c.strip() for c in (args.remove or "").split(",") if c.strip()]:
        op = client.get_type("AdGroupCriterionOperation")
        op.remove = f"customers/{cid}/adGroupCriteria/{args.ad_group}~{crit_id}"
        ops.append(op)
        plan.append(f"× remove criterion {crit_id}")
    if not ops:
        _die("Zadej --value a/nebo --remove.")

    print(f"PLÁN: ad group {args.ad_group} demografie:")
    for p in plan:
        print(f"   {p}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupCriterionService",
                         method_name="mutate_ad_group_criteria",
                         request_type="MutateAdGroupCriteriaRequest",
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"demografie ad group {args.ad_group}")
