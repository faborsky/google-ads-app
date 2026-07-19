"""Conversion actions: list, create (webpage type), update (status / primary /
counting / value). No offline import — Google steers new integrations to the
Data Manager API (since 2026-06-15).

`metrics.conversions` counts only PRIMARY actions (what Smart Bidding optimizes
to); `all_conversions` counts everything. 0 primary + non-0 all = a key action
is Secondary/HIDDEN — fix conversion config before touching bids.
"""
from __future__ import annotations

import argparse

from gads.api import (_clean_id, _field_mask, _get_client, _run_mutation,
                      _run_query, _show_result)
from gads.formatting import _die, _output_json

# Real ConversionActionCategoryEnum members (verified live 2026-07-19, v24).
# NOTE: there is no generic "LEAD" — only the specific lead subtypes.
_CATEGORIES = ["PURCHASE", "SIGNUP", "PAGE_VIEW", "DOWNLOAD", "ADD_TO_CART",
               "BEGIN_CHECKOUT", "SUBSCRIBE_PAID", "CONTACT",
               "SUBMIT_LEAD_FORM", "BOOK_APPOINTMENT", "REQUEST_QUOTE",
               "GET_DIRECTIONS", "OUTBOUND_CLICK", "ENGAGEMENT",
               "PHONE_CALL_LEAD", "IMPORTED_LEAD", "QUALIFIED_LEAD",
               "CONVERTED_LEAD", "DEFAULT"]


def cmd_conversions(args: argparse.Namespace) -> None:
    """List conversion actions with status, category and primary flag."""
    client = _get_client(args.account)
    rows = _run_query(client, _clean_id(args.customer_id), """
        SELECT conversion_action.id, conversion_action.name,
               conversion_action.status, conversion_action.type,
               conversion_action.category, conversion_action.primary_for_goal,
               conversion_action.counting_type,
               conversion_action.value_settings.default_value,
               conversion_action.value_settings.always_use_default_value,
               conversion_action.click_through_lookback_window_days
        FROM conversion_action
        WHERE conversion_action.status != 'REMOVED'
    """, args.account)
    out = [{
        "id": str(r.conversion_action.id),
        "name": r.conversion_action.name,
        "status": r.conversion_action.status.name,
        "type": r.conversion_action.type_.name,
        "category": r.conversion_action.category.name,
        "primary_for_goal": r.conversion_action.primary_for_goal,
        "counting": r.conversion_action.counting_type.name,
        "default_value": r.conversion_action.value_settings.default_value,
        "lookback_days": r.conversion_action.click_through_lookback_window_days,
    } for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádné konverzní akce.")
        return
    for c in out:
        primary = "PRIMARY  " if c["primary_for_goal"] else "secondary"
        print(f"{c['id']:>13}  {c['status']:<8} {primary} {c['category']:<16} "
              f"{c['counting']:<15} {c['name']}")


def cmd_conversion_create(args: argparse.Namespace) -> None:
    """Create a WEBPAGE conversion action (tag/GTM fires it)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    category = args.category.upper()
    if category not in _CATEGORIES:
        _die(f"--category musí být jedna z: {', '.join(_CATEGORIES)}")

    op = client.get_type("ConversionActionOperation")
    ca = op.create
    ca.name = args.name
    ca.type_ = client.enums.ConversionActionTypeEnum.WEBPAGE
    ca.category = client.enums.ConversionActionCategoryEnum[category]
    ca.status = client.enums.ConversionActionStatusEnum.ENABLED
    ca.primary_for_goal = args.primary
    ca.counting_type = client.enums.ConversionActionCountingTypeEnum[
        "ONE_PER_CLICK" if args.counting == "one" else "MANY_PER_CLICK"]
    if args.value is not None:
        ca.value_settings.default_value = float(args.value)
        ca.value_settings.always_use_default_value = True

    primary = "PRIMARY (bidding na ni optimalizuje)" if args.primary else "secondary (jen měření)"
    print(f"PLÁN: nová konverzní akce '{args.name}' — {category}, {primary}, "
          f"counting {args.counting}"
          + (f", výchozí hodnota {args.value}" if args.value is not None else ""))
    resp = _run_mutation(client, args.account, cid,
                         service_name="ConversionActionService",
                         method_name="mutate_conversion_actions",
                         request_type="MutateConversionActionsRequest",
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"konverzní akce '{args.name}'")
        if args.confirm:
            print("   Nezapomeň: akci musí střílet tag/GTM — vytvořením v API se nic neměří.")


def cmd_conversion_update(args: argparse.Namespace) -> None:
    """Update a conversion action: status, primary/secondary, counting, value."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    svc = client.get_service("ConversionActionService")
    op = client.get_type("ConversionActionOperation")
    ca = op.update
    ca.resource_name = svc.conversion_action_path(cid, args.conversion_id)
    changes = []
    if args.status:
        ca.status = client.enums.ConversionActionStatusEnum[args.status.upper()]
        changes.append(f"status → {args.status.upper()}")
    if args.primary is not None:
        ca.primary_for_goal = args.primary == "yes"
        changes.append(f"primary_for_goal → {ca.primary_for_goal}")
    if args.counting:
        ca.counting_type = client.enums.ConversionActionCountingTypeEnum[
            "ONE_PER_CLICK" if args.counting == "one" else "MANY_PER_CLICK"]
        changes.append(f"counting → {args.counting}")
    if args.value is not None:
        ca.value_settings.default_value = float(args.value)
        ca.value_settings.always_use_default_value = True
        changes.append(f"default value → {args.value}")
    if not changes:
        _die("Zadej aspoň jednu změnu (--status / --primary / --counting / --value).")
    client.copy_from(op.update_mask, _field_mask(client, ca))

    print(f"PLÁN: konverzní akce {args.conversion_id}: {', '.join(changes)}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="ConversionActionService",
                         method_name="mutate_conversion_actions",
                         request_type="MutateConversionActionsRequest",
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"konverzní akce {args.conversion_id}")
