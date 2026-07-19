"""Ads: list (with policy status), RSA create (with preflight lint), status,
final-URL update, policy detail.

⚠️ Ad creative is IMMUTABLE in Google Ads — only URL fields can be updated in
place. Changing text = create a new RSA + remove the old one. A status update
to REMOVED silently no-ops; removal needs a remove operation (cmd_ad_status
handles this).
"""
from __future__ import annotations

import argparse

from gads.api import (_clean_id, _field_mask, _get_client,
                      _require_paused_before_remove, _run_mutation, _run_query,
                      _show_result)
from gads.formatting import _die, _output_json
from gads.lint import lint_rsa


def cmd_ads(args: argparse.Namespace) -> None:
    """List RSAs with status, Ad Strength and policy approval status."""
    client = _get_client(args.account)
    where = "WHERE ad_group_ad.status != 'REMOVED' AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'"
    if args.ad_group:
        where += f" AND ad_group.id = {args.ad_group}"
    if args.campaign:
        where += f" AND campaign.id = {args.campaign}"
    gaql = f"""
        SELECT ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.ad_strength,
               ad_group_ad.policy_summary.approval_status,
               ad_group_ad.policy_summary.review_status,
               ad_group_ad.ad.final_urls,
               ad_group_ad.ad.responsive_search_ad.headlines,
               ad_group.id, ad_group.name, campaign.name
        FROM ad_group_ad
        {where}
        ORDER BY campaign.name, ad_group.name
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = []
    for r in rows:
        aga = r.ad_group_ad
        out.append({
            "ad_id": str(aga.ad.id),
            "ad_group_id": str(r.ad_group.id),
            "ad_group": r.ad_group.name,
            "campaign": r.campaign.name,
            "status": aga.status.name,
            "ad_strength": aga.ad_strength.name,
            "approval_status": aga.policy_summary.approval_status.name,
            "review_status": aga.policy_summary.review_status.name,
            "final_urls": list(aga.ad.final_urls),
            "headlines": [h.text for h in aga.ad.responsive_search_ad.headlines],
        })
    if args.json:
        _output_json(out)
        return
    if not out:
        print("No ads found.")
        return
    for a in out:
        flag = "" if a["approval_status"] == "APPROVED" else f"  ⚠️ {a['approval_status']}"
        print(f"{a['ad_id']:>12}  {a['status']:<8}  {a['ad_strength']:<12} "
              f"{a['approval_status']:<18} {a['ad_group'][:22]:<22} "
              f"{(a['headlines'][0] if a['headlines'] else '?')[:38]}{flag}")


def cmd_ad_policy(args: argparse.Namespace) -> None:
    """Policy detail: approval/review status + policy topics per ad.

    Use after creating ads — Google reviews asynchronously (typically within
    1 business day). --only-problems hides APPROVED ads.
    """
    client = _get_client(args.account)
    where = "WHERE ad_group_ad.status != 'REMOVED'"
    if args.ad_group:
        where += f" AND ad_group.id = {args.ad_group}"
    if args.campaign:
        where += f" AND campaign.id = {args.campaign}"
    if args.only_problems:
        where += " AND ad_group_ad.policy_summary.approval_status != 'APPROVED'"
    gaql = f"""
        SELECT ad_group_ad.ad.id, ad_group_ad.status,
               ad_group_ad.policy_summary.approval_status,
               ad_group_ad.policy_summary.review_status,
               ad_group_ad.policy_summary.policy_topic_entries,
               ad_group.id, ad_group.name, campaign.name
        FROM ad_group_ad
        {where}
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = []
    for r in rows:
        ps = r.ad_group_ad.policy_summary
        out.append({
            "ad_id": str(r.ad_group_ad.ad.id),
            "ad_group_id": str(r.ad_group.id),
            "ad_group": r.ad_group.name,
            "campaign": r.campaign.name,
            "approval_status": ps.approval_status.name,
            "review_status": ps.review_status.name,
            "policy_topics": [{
                "topic": e.topic,
                "type": e.type_.name,
            } for e in ps.policy_topic_entries],
        })
    if args.json:
        _output_json(out)
        return
    if not out:
        print("Žádné inzeráty" + (" s policy problémem. ✅" if args.only_problems else "."))
        return
    for a in out:
        icon = {"APPROVED": "✅", "APPROVED_LIMITED": "🟡", "DISAPPROVED": "🔴"}.get(a["approval_status"], "⏳")
        print(f"{icon} ad {a['ad_id']}  {a['approval_status']:<18} review:{a['review_status']:<20} "
              f"{a['campaign'][:20]} / {a['ad_group'][:20]}")
        for t in a["policy_topics"]:
            print(f"     - [{t['type']}] {t['topic']}")


# Inline pin syntax: "AI First @H1" pins to HEADLINE_1; "text @D1" to DESCRIPTION_1.
# Pinning to position 1 is how you keep your brand/domain always visible — the
# fix for Limited Ad Serving "generic / unclear brand" flags.
_PIN_MAP = {
    "H1": "HEADLINE_1", "H2": "HEADLINE_2", "H3": "HEADLINE_3",
    "D1": "DESCRIPTION_1", "D2": "DESCRIPTION_2",
}


def _split_pin(raw: str) -> tuple[str, str | None]:
    """'AI First @H1' -> ('AI First', 'HEADLINE_1'); 'text' -> ('text', None)."""
    s = raw.strip()
    if " @" in s:
        base, _, tag = s.rpartition(" @")
        tag = tag.strip().upper()
        if tag in _PIN_MAP:
            return base.strip(), _PIN_MAP[tag]
    return s, None


def cmd_rsa_create(args: argparse.Namespace) -> None:
    """Create a responsive search ad. Headlines/descriptions are pipe-separated.

    Pin an asset with a trailing ` @H1`/`@H2`/`@H3` (headlines) or ` @D1`/`@D2`
    (descriptions) — e.g. `AI First @H1` keeps the brand in position 1.
    Preflight lint runs BEFORE any API call (counts/lengths hard-fail, style
    findings warn); validate_only remains the final arbiter.
    """
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    headlines = [_split_pin(h) for h in args.headlines.split("|") if h.strip()]
    descriptions = [_split_pin(d) for d in args.descriptions.split("|") if d.strip()]
    lint_rsa([t for t, _ in headlines], [t for t, _ in descriptions],
             args.path1, args.path2)
    bad_h = [t for t, p in headlines if p and not p.startswith("HEADLINE")]
    bad_d = [t for t, p in descriptions if p and not p.startswith("DESCRIPTION")]
    if bad_h:
        _die(f"Headline lze připnout jen na H1/H2/H3: {bad_h}")
    if bad_d:
        _die(f"Description lze připnout jen na D1/D2: {bad_d}")

    ag_service = client.get_service("AdGroupService")
    op = client.get_type("AdGroupAdOperation")
    aga = op.create
    aga.status = client.enums.AdGroupAdStatusEnum.ENABLED
    aga.ad_group = ag_service.ad_group_path(cid, args.ad_group)
    aga.ad.final_urls.append(args.final_url)
    for text, pin in headlines:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        if pin:
            asset.pinned_field = client.enums.ServedAssetFieldTypeEnum[pin]
        aga.ad.responsive_search_ad.headlines.append(asset)
    for text, pin in descriptions:
        asset = client.get_type("AdTextAsset")
        asset.text = text
        if pin:
            asset.pinned_field = client.enums.ServedAssetFieldTypeEnum[pin]
        aga.ad.responsive_search_ad.descriptions.append(asset)
    if args.path1:
        aga.ad.responsive_search_ad.path1 = args.path1
    if args.path2:
        aga.ad.responsive_search_ad.path2 = args.path2

    pins = [f"{t}→{p}" for t, p in headlines + descriptions if p]
    print(f"PLÁN: nová RSA v ad group {args.ad_group} — "
          f"{len(headlines)} headlines, {len(descriptions)} descriptions, URL {args.final_url}")
    if pins:
        print(f"      připnuto: {', '.join(pins)}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupAdService", method_name="mutate_ad_group_ads",
                         request_type="MutateAdGroupAdsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, "responsive search ad")
        if args.confirm:
            print("   Google inzerát schvaluje asynchronně (typicky do 1 pracovního dne)"
                  " — zkontroluj pak `ad-policy`.")


def cmd_ad_status(args: argparse.Namespace) -> None:
    """Enable / pause / remove a single ad within an ad group. REMOVED is
    permanent → requires the ad to be PAUSED first."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    op = client.get_type("AdGroupAdOperation")
    rn = f"customers/{cid}/adGroupAds/{args.ad_group_id}~{args.ad_id}"
    if args.status == "removed":
        _require_paused_before_remove(
            client, args.account, cid,
            gaql=f"SELECT ad_group_ad.status FROM ad_group_ad "
                 f"WHERE ad_group.id = {args.ad_group_id} AND ad_group_ad.ad.id = {args.ad_id}",
            entity_label=f"reklama {args.ad_id}", force=args.force)
        # REMOVED cannot be set via an update — it requires a remove operation.
        op.remove = rn
    else:
        aga = op.update
        aga.resource_name = rn
        aga.status = client.enums.AdGroupAdStatusEnum[args.status.upper()]
        client.copy_from(op.update_mask, _field_mask(client, aga))
    print(f"PLÁN: reklama {args.ad_id} (sestava {args.ad_group_id}) → status {args.status.upper()}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdGroupAdService", method_name="mutate_ad_group_ads",
                         request_type="MutateAdGroupAdsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"reklama {args.ad_id} → {args.status.upper()}")


def cmd_ad_update_url(args: argparse.Namespace) -> None:
    """Update the Final URL on an existing ad (keeps the ad's performance history)."""
    client = _get_client(args.account)
    cid = _clean_id(args.customer_id)
    service = client.get_service("AdService")
    op = client.get_type("AdOperation")
    ad = op.update
    ad.resource_name = service.ad_path(cid, args.ad_id)
    ad.final_urls.append(args.final_url)
    client.copy_from(op.update_mask, _field_mask(client, ad))

    print(f"PLÁN: reklama {args.ad_id} → Final URL: {args.final_url}")
    resp = _run_mutation(client, args.account, cid,
                         service_name="AdService", method_name="mutate_ads",
                         request_type="MutateAdsRequest", operations=[op], confirm=args.confirm)
    if resp is not None:
        _show_result(resp, args.confirm, f"reklama {args.ad_id} → {args.final_url}")
