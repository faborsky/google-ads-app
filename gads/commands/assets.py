"""Assets (sitelinks, callouts, structured snippets): create, list, link/unlink
to customer/campaign/ad group.

⚠️ Assets are CREATE-ONLY in the API — once created they cannot be edited or
deleted, you only manage the LINKS. "Editing" = create a new asset + relink.
Feed-based extensions no longer exist (removed in v19) — assets are the only
path. Lower level overrides higher (ad-group sitelinks suppress campaign ones).
Search needs ≥2 sitelinks to serve them.
"""
from __future__ import annotations

import argparse
import json

from gads.api import _clean_id, _get_client, _run_mutation, _run_query, _show_result
from gads.formatting import _die, _output_json
from gads.lint import (CALLOUT_MAX, SITELINK_DESC_MAX, SITELINK_TEXT_MAX,
                       SNIPPET_HEADERS, SNIPPET_VALUE_MAX, SNIPPET_VALUES_RANGE,
                       lint_texts)

_FIELD_TYPES = {"sitelink": "SITELINK", "callout": "CALLOUT",
                "snippet": "STRUCTURED_SNIPPET"}
_ASSET_TYPES = {"sitelink": "SITELINK", "callout": "CALLOUT",
                "snippet": "STRUCTURED_SNIPPET"}


def cmd_assets(args: argparse.Namespace) -> None:
    """List text assets (sitelink/callout/structured snippet) with their IDs."""
    client = _get_client(args.account)
    where = "WHERE asset.type IN ('SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET')"
    if args.type:
        where = f"WHERE asset.type = '{_ASSET_TYPES[args.type]}'"
    gaql = f"""
        SELECT asset.id, asset.type, asset.name,
               asset.sitelink_asset.link_text,
               asset.sitelink_asset.description1, asset.sitelink_asset.description2,
               asset.callout_asset.callout_text,
               asset.structured_snippet_asset.header,
               asset.structured_snippet_asset.values,
               asset.final_urls
        FROM asset
        {where}
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = []
    for r in rows:
        a = r.asset
        item = {"id": str(a.id), "type": a.type_.name}
        if a.type_.name == "SITELINK":
            item.update({"text": a.sitelink_asset.link_text,
                         "description1": a.sitelink_asset.description1,
                         "description2": a.sitelink_asset.description2,
                         "final_urls": list(a.final_urls)})
        elif a.type_.name == "CALLOUT":
            item["text"] = a.callout_asset.callout_text
        else:
            item.update({"header": a.structured_snippet_asset.header,
                         "values": list(a.structured_snippet_asset.values)})
        out.append(item)
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádné assety.")
        return
    for a in out:
        detail = (a.get("text") or f"{a.get('header')}: {', '.join(a.get('values', []))}")
        url = f"  → {a['final_urls'][0]}" if a.get("final_urls") else ""
        print(f"{a['id']:>13}  {a['type']:<20} {detail}{url}")


def cmd_asset_links(args: argparse.Namespace) -> None:
    """Where are assets linked: customer + campaign + ad-group level (3 queries)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    out = []
    for level, resource, extra in (
        ("customer", "customer_asset", ""),
        ("campaign", "campaign_asset", ", campaign.id, campaign.name"),
        ("ad_group", "ad_group_asset", ", ad_group.id, ad_group.name, campaign.name"),
    ):
        gaql = f"""
            SELECT {resource}.asset, {resource}.field_type, {resource}.status{extra}
            FROM {resource}
            WHERE {resource}.status != 'REMOVED'
              AND {resource}.field_type IN ('SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET')
        """
        for r in _run_query(client, cid, gaql, args.account):
            la = getattr(r, resource)
            item = {
                "level": level,
                "asset_id": la.asset.split("/")[-1],
                "field_type": la.field_type.name,
            }
            if level == "campaign":
                item.update({"campaign_id": str(r.campaign.id), "campaign": r.campaign.name})
            elif level == "ad_group":
                item.update({"ad_group_id": str(r.ad_group.id), "ad_group": r.ad_group.name,
                             "campaign": r.campaign.name})
            out.append(item)
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádné napojené assety (sitelink/callout/snippet).")
        return
    for l in out:
        target = (l.get("campaign") or l.get("ad_group") or "účet")
        print(f"asset {l['asset_id']:>13}  {l['field_type']:<20} {l['level']:<9} {target}")


def cmd_sitelink_create(args: argparse.Namespace) -> None:
    """Create sitelink assets from JSON:
    [{"text":"Kurz","url":"https://…","desc1":"…","desc2":"…"}, …]
    (link_text ≤25; desc1+desc2 ≤35 each, both or neither).
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    try:
        items = json.loads(args.sitelinks_json)
    except json.JSONDecodeError as ex:
        _die(f"Neplatný JSON: {ex}")
    if not items:
        _die("Prázdný seznam sitelinků.")
    lint_texts([i["text"] for i in items], max_len=SITELINK_TEXT_MAX, label="sitelink text")
    descs = [i[k] for i in items for k in ("desc1", "desc2") if i.get(k)]
    if descs:
        lint_texts(descs, max_len=SITELINK_DESC_MAX, label="sitelink description")
    for i in items:
        if bool(i.get("desc1")) != bool(i.get("desc2")):
            _die(f"Sitelink '{i['text']}': desc1 a desc2 musí být oba, nebo žádný.")

    ops = []
    for i in items:
        op = client.get_type("AssetOperation")
        a = op.create
        a.sitelink_asset.link_text = i["text"]
        if i.get("desc1"):
            a.sitelink_asset.description1 = i["desc1"]
            a.sitelink_asset.description2 = i["desc2"]
        a.final_urls.append(i["url"])
        ops.append(op)

    print(f"PLÁN: vytvořit {len(ops)} sitelink assetů:")
    for i in items:
        print(f"   {i['text']} → {i['url']}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AssetService", method_name="mutate_assets",
                         request_type="MutateAssetsRequest", operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"{len(ops)} sitelinků")
        if args.confirm:
            print("   Napoj je: `asset-link --asset <id,id> --field-type sitelink "
                  "--campaign <id>` (pro zobrazování potřebuješ ≥2).")


def cmd_callout_create(args: argparse.Namespace) -> None:
    """Create callout assets (pipe-separated, ≤25 chars each)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    texts = [t.strip() for t in args.texts.split("|") if t.strip()]
    if not texts:
        _die("Zadej --texts 'a|b|c'.")
    lint_texts(texts, max_len=CALLOUT_MAX, label="callout")

    ops = []
    for t in texts:
        op = client.get_type("AssetOperation")
        op.create.callout_asset.callout_text = t
        ops.append(op)

    print(f"PLÁN: vytvořit {len(ops)} callout assetů: {', '.join(texts)}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AssetService", method_name="mutate_assets",
                         request_type="MutateAssetsRequest", operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"{len(ops)} calloutů")


def cmd_snippet_create(args: argparse.Namespace) -> None:
    """Create a structured snippet asset. Header must be one of Google's fixed
    (English) headers; values 3–10 × ≤25 chars."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    if args.header not in SNIPPET_HEADERS:
        _die(f"Header musí být jeden z: {', '.join(SNIPPET_HEADERS)} "
             f"(anglicky — Google je lokalizuje sám).")
    values = [v.strip() for v in args.values.split("|") if v.strip()]
    lo, hi = SNIPPET_VALUES_RANGE
    if not (lo <= len(values) <= hi):
        _die(f"Structured snippet potřebuje {lo}–{hi} hodnot (máš {len(values)}).")
    lint_texts(values, max_len=SNIPPET_VALUE_MAX, label="snippet hodnota")

    op = client.get_type("AssetOperation")
    a = op.create
    a.structured_snippet_asset.header = args.header
    a.structured_snippet_asset.values.extend(values)

    print(f"PLÁN: structured snippet '{args.header}': {', '.join(values)}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AssetService", method_name="mutate_assets",
                         request_type="MutateAssetsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, "structured snippet")


def _link_ops(client, cid, args, *, create: bool):
    """Build CustomerAsset/CampaignAsset/AdGroupAsset ops for asset-link/unlink."""
    field_type = _FIELD_TYPES.get(args.field_type)
    if not field_type:
        _die(f"--field-type musí být {', '.join(_FIELD_TYPES)}.")
    asset_ids = [a.strip() for a in args.asset.split(",") if a.strip()]
    if not asset_ids:
        _die("Zadej --asset id[,id…].")
    asset_service = client.get_service("AssetService")

    if args.campaign:
        svc, op_type, req = ("CampaignAssetService", "CampaignAssetOperation",
                             "MutateCampaignAssetsRequest")
        parent_rn = client.get_service("CampaignService").campaign_path(cid, args.campaign)
        parent_field, parent_id = "campaign", args.campaign
        scope = f"kampaň {args.campaign}"
    elif args.ad_group:
        svc, op_type, req = ("AdGroupAssetService", "AdGroupAssetOperation",
                             "MutateAdGroupAssetsRequest")
        parent_rn = client.get_service("AdGroupService").ad_group_path(cid, args.ad_group)
        parent_field, parent_id = "ad_group", args.ad_group
        scope = f"ad group {args.ad_group}"
    elif args.customer:
        svc, op_type, req = ("CustomerAssetService", "CustomerAssetOperation",
                             "MutateCustomerAssetsRequest")
        parent_rn, parent_field, parent_id = None, None, None
        scope = "celý účet"
    else:
        _die("Zadej --campaign, --ad-group, nebo --customer.")
        return None

    ops = []
    for aid in asset_ids:
        op = client.get_type(op_type)
        if create:
            link = op.create
            link.asset = asset_service.asset_path(cid, aid)
            link.field_type = client.enums.AssetFieldTypeEnum[field_type]
            if parent_field:
                setattr(link, parent_field, parent_rn)
        else:
            entity = {"CampaignAssetService": "campaignAssets",
                      "AdGroupAssetService": "adGroupAssets",
                      "CustomerAssetService": "customerAssets"}[svc]
            frag = f"{parent_id}~{aid}~{field_type}" if parent_id else f"{aid}~{field_type}"
            op.remove = f"customers/{cid}/{entity}/{frag}"
        ops.append(op)
    return svc, req, ops, scope, asset_ids


def cmd_asset_link(args: argparse.Namespace) -> None:
    """Link assets to customer / campaign / ad group."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    built = _link_ops(client, cid, args, create=True)
    if not built:
        return
    svc, req, ops, scope, asset_ids = built
    print(f"PLÁN: napojit assety {', '.join(asset_ids)} ({args.field_type}) na {scope}")
    method = {"CampaignAssetService": "mutate_campaign_assets",
              "AdGroupAssetService": "mutate_ad_group_assets",
              "CustomerAssetService": "mutate_customer_assets"}[svc]
    resp = _run_mutation(client, args.account, cid, service_name=svc,
                         method_name=method, request_type=req,
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"{len(ops)} asset linků na {scope}")


def cmd_asset_unlink(args: argparse.Namespace) -> None:
    """Unlink assets from customer / campaign / ad group (the asset itself
    cannot be deleted — API assets are create-only)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    built = _link_ops(client, cid, args, create=False)
    if not built:
        return
    svc, req, ops, scope, asset_ids = built
    print(f"PLÁN: odpojit assety {', '.join(asset_ids)} ({args.field_type}) z {scope}")
    method = {"CampaignAssetService": "mutate_campaign_assets",
              "AdGroupAssetService": "mutate_ad_group_assets",
              "CustomerAssetService": "mutate_customer_assets"}[svc]
    resp = _run_mutation(client, args.account, cid, service_name=svc,
                         method_name=method, request_type=req,
                         operations=ops, confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"odpojeno {len(ops)} z {scope}")
