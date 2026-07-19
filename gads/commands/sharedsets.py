"""Shared sets — shared negative keyword lists + account-level negatives.

Flow: shared-set-create (SharedSet) → shared-set-add (SharedCriterion per
keyword) → shared-set-attach (CampaignSharedSet). Account-level negatives =
a shared set of type ACCOUNT_LEVEL_NEGATIVE_KEYWORDS attached via
CustomerNegativeCriterion.negative_keyword_list (max 1000 keywords/account).
Limits: 20 lists/account, 5000 negatives/list.
"""
from __future__ import annotations

import argparse

from gads.api import _clean_id, _get_client, _run_mutation, _run_query, _show_result
from gads.formatting import _die, _output_json

_SET_TYPES = {"negative-keywords": "NEGATIVE_KEYWORDS",
              "account-negatives": "ACCOUNT_LEVEL_NEGATIVE_KEYWORDS"}


def cmd_shared_sets(args: argparse.Namespace) -> None:
    """List shared sets (negative keyword lists) + where they're attached."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rows = _run_query(client, cid, """
        SELECT shared_set.id, shared_set.name, shared_set.type,
               shared_set.member_count, shared_set.reference_count
        FROM shared_set
        WHERE shared_set.status != 'REMOVED'
    """, args.account)
    sets = [{
        "id": str(r.shared_set.id),
        "name": r.shared_set.name,
        "type": r.shared_set.type_.name,
        "keywords": r.shared_set.member_count,
        "campaigns_attached": r.shared_set.reference_count,
    } for r in rows]

    attachments = []
    if sets:
        for r in _run_query(client, cid, """
            SELECT campaign.id, campaign.name, campaign_shared_set.shared_set
            FROM campaign_shared_set
            WHERE campaign_shared_set.status != 'REMOVED'
        """, args.account):
            attachments.append({
                "campaign_id": str(r.campaign.id),
                "campaign": r.campaign.name,
                "shared_set_id": r.campaign_shared_set.shared_set.split("/")[-1],
            })
    if args.json:
        _output_json({"sets": sets, "attachments": attachments})
        return
    if not sets:
        print("Žádné shared sety.")
        return
    for s in sets:
        att = [a["campaign"] for a in attachments if a["shared_set_id"] == s["id"]]
        print(f"{s['id']:>13}  {s['type']:<32} {s['keywords']:>4} KW  "
              f"kampaní: {s['campaigns_attached']}  {s['name']}")
        for a in att:
            print(f"               ↳ {a}")


def cmd_shared_set_create(args: argparse.Namespace) -> None:
    """Create a shared negative keyword list (or account-level negatives set)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    set_type = _SET_TYPES.get(args.type)
    if not set_type:
        _die(f"--type musí být {' | '.join(_SET_TYPES)}.")
    op = client.get_type("SharedSetOperation")
    ss = op.create
    ss.name = args.name
    ss.type_ = client.enums.SharedSetTypeEnum[set_type]

    print(f"PLÁN: nový shared set '{args.name}' ({set_type})")
    resp = _run_mutation(client, args.account, cid,
                         service_name="SharedSetService", method_name="mutate_shared_sets",
                         request_type="MutateSharedSetsRequest", operations=[op],
                         confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"shared set '{args.name}'")
        if args.confirm:
            nxt = ("customer-negatives-attach" if args.type == "account-negatives"
                   else "shared-set-attach")
            print(f"   Naplň ho: `shared-set-add --set <id> --keywords \"a,b\"`, "
                  f"pak připoj: `{nxt}`.")


def cmd_shared_set_add(args: argparse.Namespace) -> None:
    """Add negative keywords into a shared set."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    terms = [t.strip() for t in args.keywords.split(",") if t.strip()]
    if not terms:
        _die("Zadej --keywords 'a,b,c'.")
    match_type = client.enums.KeywordMatchTypeEnum[args.match_type.upper()]
    ss_service = client.get_service("SharedSetService")

    ops = []
    for t in terms:
        op = client.get_type("SharedCriterionOperation")
        sc = op.create
        sc.shared_set = ss_service.shared_set_path(cid, args.set)
        sc.keyword.text = t
        sc.keyword.match_type = match_type
        ops.append(op)

    print(f"PLÁN: přidat {len(ops)} negativ ({args.match_type}) do shared setu {args.set}:")
    for t in terms:
        print(f"   −{t}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="SharedCriterionService",
                         method_name="mutate_shared_criteria",
                         request_type="MutateSharedCriteriaRequest",
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"{len(ops)} negativ do setu {args.set}")


def cmd_shared_set_list_keywords(args: argparse.Namespace) -> None:
    """List keywords inside a shared set (with criterion IDs for removal)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    rows = _run_query(client, cid, f"""
        SELECT shared_criterion.criterion_id, shared_criterion.keyword.text,
               shared_criterion.keyword.match_type
        FROM shared_criterion
        WHERE shared_set.id = {args.set}
    """, args.account)
    out = [{
        "criterion_id": str(r.shared_criterion.criterion_id),
        "text": r.shared_criterion.keyword.text,
        "match_type": r.shared_criterion.keyword.match_type.name,
    } for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Set je prázdný.")
        return
    for k in out:
        print(f"{k['criterion_id']:>13}  [{k['match_type']:<6}] −{k['text']}")


def cmd_shared_set_remove_keywords(args: argparse.Namespace) -> None:
    """Remove criteria from a shared set (IDs from shared-set-keywords)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    ids = [i.strip() for i in args.criteria.split(",") if i.strip()]
    if not ids:
        _die("Zadej --criteria id1,id2,…")
    ops = []
    for i in ids:
        op = client.get_type("SharedCriterionOperation")
        op.remove = f"customers/{cid}/sharedCriteria/{args.set}~{i}"
        ops.append(op)
    print(f"PLÁN: odebrat {len(ops)} kritérií ze setu {args.set}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="SharedCriterionService",
                         method_name="mutate_shared_criteria",
                         request_type="MutateSharedCriteriaRequest",
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"odebráno {len(ops)} kritérií")


def cmd_shared_set_attach(args: argparse.Namespace) -> None:
    """Attach a shared set to campaign(s) — or detach with --detach."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    campaign_ids = [c.strip() for c in args.campaigns.split(",") if c.strip()]
    if not campaign_ids:
        _die("Zadej --campaigns id1,id2,…")
    c_service = client.get_service("CampaignService")
    ss_service = client.get_service("SharedSetService")

    ops = []
    for camp in campaign_ids:
        op = client.get_type("CampaignSharedSetOperation")
        if args.detach:
            op.remove = f"customers/{cid}/campaignSharedSets/{camp}~{args.set}"
        else:
            css = op.create
            css.campaign = c_service.campaign_path(cid, camp)
            css.shared_set = ss_service.shared_set_path(cid, args.set)
        ops.append(op)

    verb = "odpojit od" if args.detach else "připojit k"
    print(f"PLÁN: shared set {args.set} {verb} kampaním: {', '.join(campaign_ids)}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CampaignSharedSetService",
                         method_name="mutate_campaign_shared_sets",
                         request_type="MutateCampaignSharedSetsRequest",
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm,
                     f"shared set {args.set} ↔ {len(campaign_ids)} kampaní")


def cmd_shared_set_remove(args: argparse.Namespace) -> None:
    """Remove a whole shared set (detaches from campaigns; criteria go with it)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("SharedSetOperation")
    op.remove = f"customers/{cid}/sharedSets/{args.set}"
    print(f"PLÁN: smazat shared set {args.set} (vč. obsahu; REMOVED je trvalé)")
    resp = _run_mutation(client, args.account, cid,
                         service_name="SharedSetService", method_name="mutate_shared_sets",
                         request_type="MutateSharedSetsRequest", operations=[op],
                         confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"smazán shared set {args.set}")


def cmd_customer_negatives_attach(args: argparse.Namespace) -> None:
    """Attach an ACCOUNT_LEVEL_NEGATIVE_KEYWORDS shared set to the whole
    account (CustomerNegativeCriterion.negative_keyword_list)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("CustomerNegativeCriterionOperation")
    crit = op.create
    crit.negative_keyword_list.shared_set = (
        client.get_service("SharedSetService").shared_set_path(cid, args.set))

    print(f"PLÁN: shared set {args.set} jako ACCOUNT-LEVEL negativa (celý účet)")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CustomerNegativeCriterionService",
                         method_name="mutate_customer_negative_criteria",
                         request_type="MutateCustomerNegativeCriteriaRequest",
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"account-level negativa (set {args.set})")
        if args.confirm and resp.results:
            crit_id = resp.results[0].resource_name.split("/")[-1]
            print(f"   Odpojení: `customer-negatives-detach --criterion {crit_id}`")


def cmd_customer_negatives_detach(args: argparse.Namespace) -> None:
    """Detach an account-level criterion (ID from the attach result or GAQL
    customer_negative_criterion)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("CustomerNegativeCriterionOperation")
    op.remove = f"customers/{cid}/customerNegativeCriteria/{args.criterion}"
    print(f"PLÁN: odpojit account-level criterion {args.criterion}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="CustomerNegativeCriterionService",
                         method_name="mutate_customer_negative_criteria",
                         request_type="MutateCustomerNegativeCriteriaRequest",
                         operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"odpojen account-level criterion {args.criterion}")
