"""Labels: create, list, assign/unassign to campaigns/ad groups/ads/keywords.

GAQL filtering is by label ID only (never name) — resolve the ID first via
`labels`. Limits: 100k label applications/account, 50 labels/entity.
"""
from __future__ import annotations

import argparse

from gads.api import _clean_id, _get_client, _run_mutation, _run_query, _show_result
from gads.formatting import _die, _output_json


def cmd_labels(args: argparse.Namespace) -> None:
    """List labels with IDs."""
    client = _get_client(args.account)
    rows = _run_query(client, _clean_id(args.customer_id), """
        SELECT label.id, label.name, label.status, label.text_label.description,
               label.text_label.background_color
        FROM label
        WHERE label.status != 'REMOVED'
    """, args.account)
    out = [{
        "id": str(r.label.id),
        "name": r.label.name,
        "description": r.label.text_label.description,
        "color": r.label.text_label.background_color,
    } for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádné štítky.")
        return
    for label in out:
        desc = f"  — {label['description']}" if label["description"] else ""
        print(f"{label['id']:>13}  {label['name']}{desc}")


def cmd_label_create(args: argparse.Namespace) -> None:
    """Create a label."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("LabelOperation")
    label = op.create
    label.name = args.name
    if args.description:
        label.text_label.description = args.description
    if args.color:
        label.text_label.background_color = args.color

    print(f"PLÁN: nový štítek '{args.name}'")
    resp = _run_mutation(client, args.account, cid,
                         service_name="LabelService", method_name="mutate_labels",
                         request_type="MutateLabelsRequest", operations=[op],
                         confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"štítek '{args.name}'")


def cmd_label_remove(args: argparse.Namespace) -> None:
    """Remove a label entirely (all its assignments disappear with it)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("LabelOperation")
    op.remove = client.get_service("LabelService").label_path(cid, args.label)
    print(f"PLÁN: smazat štítek {args.label} (vč. všech přiřazení)")
    resp = _run_mutation(client, args.account, cid,
                         service_name="LabelService", method_name="mutate_labels",
                         request_type="MutateLabelsRequest", operations=[op],
                         confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"smazán štítek {args.label}")


def _label_target(client, cid, args):
    """Resolve target entity → (service, op type, request, method, build_fn, scope)."""
    label_rn = client.get_service("LabelService").label_path(cid, args.label)
    if args.campaign:
        def build(op, create):
            if create:
                cl = op.create
                cl.campaign = client.get_service("CampaignService").campaign_path(cid, args.campaign)
                cl.label = label_rn
            else:
                op.remove = f"customers/{cid}/campaignLabels/{args.campaign}~{args.label}"
        return ("CampaignLabelService", "CampaignLabelOperation",
                "MutateCampaignLabelsRequest", "mutate_campaign_labels",
                build, f"kampaň {args.campaign}")
    if args.ad_group:
        def build(op, create):
            if create:
                al = op.create
                al.ad_group = client.get_service("AdGroupService").ad_group_path(cid, args.ad_group)
                al.label = label_rn
            else:
                op.remove = f"customers/{cid}/adGroupLabels/{args.ad_group}~{args.label}"
        return ("AdGroupLabelService", "AdGroupLabelOperation",
                "MutateAdGroupLabelsRequest", "mutate_ad_group_labels",
                build, f"ad group {args.ad_group}")
    if args.ad:
        try:
            ag_id, ad_id = args.ad.split("~")
        except ValueError:
            _die("--ad čekám jako 'adGroupId~adId'.")
        def build(op, create):
            if create:
                al = op.create
                al.ad_group_ad = f"customers/{cid}/adGroupAds/{ag_id}~{ad_id}"
                al.label = label_rn
            else:
                op.remove = f"customers/{cid}/adGroupAdLabels/{ag_id}~{ad_id}~{args.label}"
        return ("AdGroupAdLabelService", "AdGroupAdLabelOperation",
                "MutateAdGroupAdLabelsRequest", "mutate_ad_group_ad_labels",
                build, f"reklama {args.ad}")
    if args.keyword:
        try:
            ag_id, crit_id = args.keyword.split("~")
        except ValueError:
            _die("--keyword čekám jako 'adGroupId~criterionId'.")
        def build(op, create):
            if create:
                kl = op.create
                kl.ad_group_criterion = f"customers/{cid}/adGroupCriteria/{ag_id}~{crit_id}"
                kl.label = label_rn
            else:
                op.remove = f"customers/{cid}/adGroupCriterionLabels/{ag_id}~{crit_id}~{args.label}"
        return ("AdGroupCriterionLabelService", "AdGroupCriterionLabelOperation",
                "MutateAdGroupCriterionLabelsRequest", "mutate_ad_group_criterion_labels",
                build, f"keyword {args.keyword}")
    _die("Zadej --campaign, --ad-group, --ad 'agId~adId', nebo --keyword 'agId~critId'.")
    return None


def cmd_label_assign(args: argparse.Namespace) -> None:
    """Assign a label to a campaign / ad group / ad / keyword."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    target = _label_target(client, cid, args)
    if not target:
        return
    svc, op_type, req, method, build, scope = target
    op = client.get_type(op_type)
    build(op, create=True)
    print(f"PLÁN: štítek {args.label} → {scope}")
    resp = _run_mutation(client, args.account, cid, service_name=svc,
                         method_name=method, request_type=req,
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"štítek {args.label} na {scope}")


def cmd_label_unassign(args: argparse.Namespace) -> None:
    """Remove a label from a campaign / ad group / ad / keyword."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    target = _label_target(client, cid, args)
    if not target:
        return
    svc, op_type, req, method, build, scope = target
    op = client.get_type(op_type)
    build(op, create=False)
    print(f"PLÁN: sundat štítek {args.label} z {scope}")
    resp = _run_mutation(client, args.account, cid, service_name=svc,
                         method_name=method, request_type=req,
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"štítek {args.label} sundán z {scope}")
