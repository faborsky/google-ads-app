"""Argparse wiring + dispatch. Parser/dispatch parity is guaranteed by _cmd()
(one call = one subcommand + its handler)."""
from __future__ import annotations

import argparse

from gads import __version__
from gads.commands.account import cmd_accounts, cmd_api_limits, cmd_quota
from gads.commands.ads import (cmd_ad_policy, cmd_ad_status, cmd_ad_update_url,
                               cmd_ads, cmd_rsa_create)
from gads.commands.assets import (cmd_asset_link, cmd_asset_links,
                                  cmd_asset_unlink, cmd_assets,
                                  cmd_callout_create, cmd_sitelink_create,
                                  cmd_snippet_create)
from gads.commands.audiences import (cmd_audience_attach, cmd_audience_create,
                                     cmd_audience_detach, cmd_audience_exclude,
                                     cmd_audiences, cmd_audiences_attached)
from gads.commands.auth import cmd_auth
from gads.commands.budgets import (cmd_budget_assign, cmd_budget_create,
                                   cmd_budget_remove, cmd_budget_set,
                                   cmd_budgets)
from gads.commands.campaigns import (cmd_bidding_set, cmd_campaign_create,
                                     cmd_campaign_status, cmd_campaigns)
from gads.commands.conversions import (cmd_conversion_create,
                                       cmd_conversion_update, cmd_conversions)
from gads.commands.dsa import (cmd_dsa_ad_group_create, cmd_dsa_create,
                               cmd_dsa_setting, cmd_webpage_target_add,
                               cmd_webpage_target_remove, cmd_webpage_targets)
from gads.commands.experiments import (cmd_experiment_create,
                                       cmd_experiment_end,
                                       cmd_experiment_promote,
                                       cmd_experiment_results,
                                       cmd_experiment_schedule,
                                       cmd_experiments)
from gads.commands.groups import cmd_ad_group_create, cmd_ad_groups
from gads.commands.keywords import (cmd_keyword_add, cmd_keyword_remove,
                                    cmd_keywords, cmd_negative_add)
from gads.commands.labels import (cmd_label_assign, cmd_label_create,
                                  cmd_label_remove, cmd_label_unassign,
                                  cmd_labels)
from gads.commands.pmax import cmd_pmax, cmd_pmax_search_terms
from gads.commands.pulse import cmd_pulse
from gads.commands.recommendations import (cmd_recommendation_apply,
                                           cmd_recommendation_dismiss,
                                           cmd_recommendations)
from gads.commands.reporting import cmd_changes, cmd_query, cmd_report
from gads.commands.research import cmd_keywords_research, cmd_search_terms
from gads.commands.sharedsets import (cmd_customer_negatives_attach,
                                      cmd_customer_negatives_detach,
                                      cmd_shared_set_add,
                                      cmd_shared_set_attach,
                                      cmd_shared_set_create,
                                      cmd_shared_set_list_keywords,
                                      cmd_shared_set_remove,
                                      cmd_shared_set_remove_keywords,
                                      cmd_shared_sets)
from gads.commands.targeting import (cmd_campaign_targeting,
                                     cmd_demographic_target, cmd_demographics,
                                     cmd_device_bid, cmd_geo_suggest,
                                     cmd_geo_target, cmd_language_target,
                                     cmd_schedule_set)

from gads.api import DEFAULT_GEO_TARGET_ID, DEFAULT_LANGUAGE_ID


def _cmd(sub, name: str, func, help: str, *, cid: bool = True, write: bool = False):
    """Add a subcommand: positional customer_id (unless cid=False) and, for
    writes, --confirm (real write; default = validate-only dry-run)."""
    sp = sub.add_parser(name, help=help + (" [write]" if write else ""))
    if cid:
        sp.add_argument("customer_id", help="Customer ID (with or without dashes)")
    if write:
        sp.add_argument("--confirm", action="store_true",
                        help="Actually write (default: dry-run/plan)")
    sp.set_defaults(func=func)
    return sp


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="google_ads_cli",
        description=f"Google Ads CLI v{__version__} — search campaigns end-to-end: "
                    "reporting, research, campaign/RSA/keyword builds, assets, "
                    "audiences, targeting, policy checks. Mutations are dry-run "
                    "by default (--confirm writes).",
    )
    p.add_argument("--account", help="Named account profile from .env (default: default)")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # --- Setup & account -------------------------------------------------
    _cmd(sub, "auth", cmd_auth, "One-time OAuth flow → generate a refresh token", cid=False)
    _cmd(sub, "accounts", cmd_accounts, "List accessible accounts under the MCC", cid=False)
    _cmd(sub, "quota", cmd_quota, "Today's local operation usage vs daily cap", cid=False)
    _cmd(sub, "api-limits", cmd_api_limits, "Documented API limits + local usage", cid=False)

    # --- Pulse & reporting ----------------------------------------------
    sp = _cmd(sub, "pulse", cmd_pulse, "Account digest: totals, deltas, movers, "
              "opt score, recommendations, policy problems (5 ops)")
    sp.add_argument("--days", type=int, help="Window length (default 7, ends yesterday)")
    sp.add_argument("--date-from", dest="date_from", help="YYYY-MM-DD (with --date-to)")
    sp.add_argument("--date-to", dest="date_to", help="YYYY-MM-DD")
    sp.add_argument("--no-compare", dest="no_compare", action="store_true",
                    help="Skip the previous-window comparison (saves 1 op)")

    sp = _cmd(sub, "query", cmd_query, "Run an arbitrary GAQL query")
    sp.add_argument("--gaql", required=True, help="GAQL query string")

    sp = _cmd(sub, "report", cmd_report, "Preset performance report")
    sp.add_argument("--entity", default="campaign", help="campaign | ad_group | keyword")
    sp.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    sp.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")

    sp = _cmd(sub, "changes", cmd_changes, "Change history: who changed what "
              "(change_event ≤30 d; --sweep = change_status ≤90 d)")
    sp.add_argument("--days", type=int, help="Lookback (default 14; sweep 89)")
    sp.add_argument("--sweep", action="store_true", help="Cheap what-moved sweep (no field values)")
    sp.add_argument("--limit", type=int, help="Max rows (≤10000, default 200)")

    # --- Research --------------------------------------------------------
    sp = _cmd(sub, "keywords-research", cmd_keywords_research,
              "Keyword Planner ideas (volume/competition/CPC)")
    sp.add_argument("--seed", required=True, help="Comma-separated seed keywords")
    sp.add_argument("--language", default=DEFAULT_LANGUAGE_ID,
                    help=f"Language constant ID (default {DEFAULT_LANGUAGE_ID}=Czech)")
    sp.add_argument("--geo", default=DEFAULT_GEO_TARGET_ID,
                    help=f"Geo target constant ID (default {DEFAULT_GEO_TARGET_ID}=Czech Republic)")
    sp.add_argument("--limit", type=int, default=100, help="Max ideas to show")

    sp = _cmd(sub, "search-terms", cmd_search_terms,
              "Actual search queries (source for negatives)")
    sp.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    sp.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")

    # --- Campaigns -------------------------------------------------------
    sp = _cmd(sub, "campaigns", cmd_campaigns, "List search campaigns")
    sp.add_argument("--status", choices=["enabled", "paused", "removed"], help="Filter by status")

    sp = _cmd(sub, "campaign-create", cmd_campaign_create,
              "Create a SEARCH campaign + budget + geo/language (PAUSED)", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--budget", required=True, type=float, help="Daily budget in CZK")
    sp.add_argument("--bidding", default="manual_cpc",
                    choices=["manual_cpc", "max_conversions", "max_conversion_value",
                             "target_cpa", "target_roas"])
    sp.add_argument("--target-cpa", dest="target_cpa", type=float)
    sp.add_argument("--target-roas", dest="target_roas", type=float)
    sp.add_argument("--geo", default=DEFAULT_GEO_TARGET_ID,
                    help=f"Geo target IDs CSV (default {DEFAULT_GEO_TARGET_ID}=CZ; '' = none)")
    sp.add_argument("--language", default=DEFAULT_LANGUAGE_ID,
                    help=f"Language IDs CSV (default {DEFAULT_LANGUAGE_ID}=Czech; '' = none)")

    sp = _cmd(sub, "campaign-status", cmd_campaign_status,
              "Enable/pause/remove a campaign (REMOVED is permanent!)", write=True)
    sp.add_argument("campaign_id")
    sp.add_argument("--status", required=True, choices=["enabled", "paused", "removed"])
    sp.add_argument("--force", action="store_true",
                    help="Skip the PAUSED-before-REMOVED safety check")

    sp = _cmd(sub, "bidding-set", cmd_bidding_set, "Switch a campaign's bidding strategy", write=True)
    sp.add_argument("campaign_id")
    sp.add_argument("--strategy", required=True,
                    choices=["manual_cpc", "max_conversions", "max_conversion_value",
                             "target_cpa", "target_roas"])
    sp.add_argument("--target-cpa", dest="target_cpa", type=float, help="Target CPA in CZK")
    sp.add_argument("--target-roas", dest="target_roas", type=float, help="Target ROAS (e.g. 2.5)")

    # --- Budgets ---------------------------------------------------------
    _cmd(sub, "budgets", cmd_budgets, "List budgets (incl. shared + recommended amounts)")

    sp = _cmd(sub, "budget-set", cmd_budget_set, "Set a campaign's daily budget (CZK)", write=True)
    sp.add_argument("campaign_id")
    sp.add_argument("--amount", required=True, type=float, help="Daily budget in CZK")

    sp = _cmd(sub, "budget-create", cmd_budget_create, "Create a SHARED daily budget", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--amount", required=True, type=float, help="Daily budget in CZK")

    sp = _cmd(sub, "budget-assign", cmd_budget_assign,
              "Point campaign(s) at a (shared) budget", write=True)
    sp.add_argument("--budget-id", dest="budget_id", required=True)
    sp.add_argument("--campaigns", required=True, help="Campaign IDs CSV")

    sp = _cmd(sub, "budget-remove", cmd_budget_remove,
              "Remove an orphan budget (no campaigns attached)", write=True)
    sp.add_argument("--budget-id", dest="budget_id", required=True)

    # --- Ad groups -------------------------------------------------------
    sp = _cmd(sub, "ad-groups", cmd_ad_groups, "List ad groups")
    sp.add_argument("--campaign", help="Filter by campaign ID")

    sp = _cmd(sub, "ad-group-create", cmd_ad_group_create, "Create an ad group", write=True)
    sp.add_argument("--campaign", required=True, help="Campaign ID")
    sp.add_argument("--name", required=True)
    sp.add_argument("--cpc", type=float, help="Default CPC bid in CZK")

    # --- Ads -------------------------------------------------------------
    sp = _cmd(sub, "ads", cmd_ads, "List RSAs with status, Ad Strength, approval")
    sp.add_argument("--ad-group", dest="ad_group", help="Filter by ad group ID")
    sp.add_argument("--campaign", help="Filter by campaign ID")

    sp = _cmd(sub, "ad-policy", cmd_ad_policy,
              "Policy check: approval status + policy topics per ad")
    sp.add_argument("--ad-group", dest="ad_group", help="Filter by ad group ID")
    sp.add_argument("--campaign", help="Filter by campaign ID")
    sp.add_argument("--only-problems", dest="only_problems", action="store_true",
                    help="Show only non-APPROVED ads")

    sp = _cmd(sub, "rsa-create", cmd_rsa_create, "Create a responsive search ad", write=True)
    sp.add_argument("--ad-group", dest="ad_group", required=True, help="Ad group ID")
    sp.add_argument("--headlines", required=True,
                    help="Pipe-separated, 3–15 items, ≤30 chars each. Pin with a trailing "
                         "' @H1'/'@H2'/'@H3' (e.g. 'AI First @H1' keeps the brand in position 1).")
    sp.add_argument("--descriptions", required=True,
                    help="Pipe-separated, 2–4 items, ≤90 chars each. Pin with ' @D1'/'@D2'.")
    sp.add_argument("--final-url", dest="final_url", required=True)
    sp.add_argument("--path1")
    sp.add_argument("--path2")

    sp = _cmd(sub, "ad-status", cmd_ad_status,
              "Enable/pause/remove a single ad (REMOVED is permanent!)", write=True)
    sp.add_argument("ad_group_id")
    sp.add_argument("ad_id")
    sp.add_argument("--status", required=True, choices=["enabled", "paused", "removed"])
    sp.add_argument("--force", action="store_true",
                    help="Skip the PAUSED-before-REMOVED safety check")

    sp = _cmd(sub, "ad-update-url", cmd_ad_update_url,
              "Update Final URL on an existing ad (keeps history)", write=True)
    sp.add_argument("ad_id")
    sp.add_argument("--final-url", dest="final_url", required=True)

    # --- Keywords & negatives -------------------------------------------
    sp = _cmd(sub, "keywords", cmd_keywords, "List keywords (with criterion IDs)")
    sp.add_argument("--ad-group", dest="ad_group", help="Filter by ad group ID")
    sp.add_argument("--campaign", help="Filter by campaign ID")

    sp = _cmd(sub, "keyword-add", cmd_keyword_add, "Batch-add positive keywords (JSON)", write=True)
    sp.add_argument("--ad-group", dest="ad_group", required=True, help="Ad group ID")
    sp.add_argument("--keywords-json", dest="keywords_json", required=True,
                    help='JSON array: [{"text":"...","match_type":"phrase","cpc":25}]')

    sp = _cmd(sub, "keyword-remove", cmd_keyword_remove, "Remove keyword criteria", write=True)
    sp.add_argument("--criteria", required=True,
                    help="Comma-separated 'adGroupId~criterionId' fragments")

    sp = _cmd(sub, "negative-add", cmd_negative_add,
              "Add negative keywords (ad-group or campaign)", write=True)
    sp.add_argument("--ad-group", dest="ad_group", help="Ad group ID (ad-group-level)")
    sp.add_argument("--campaign", help="Campaign ID (campaign-level)")
    sp.add_argument("--keywords", required=True, help="Comma-separated negative terms")
    sp.add_argument("--match-type", dest="match_type", default="phrase",
                    choices=["exact", "phrase", "broad"])

    # --- Shared sets (negativ lists) ------------------------------------
    _cmd(sub, "shared-sets", cmd_shared_sets, "List shared negative-keyword sets + attachments")

    sp = _cmd(sub, "shared-set-create", cmd_shared_set_create,
              "Create a shared negative keyword list", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--type", default="negative-keywords",
                    choices=["negative-keywords", "account-negatives"])

    sp = _cmd(sub, "shared-set-add", cmd_shared_set_add,
              "Add negative keywords into a shared set", write=True)
    sp.add_argument("--set", required=True, help="Shared set ID")
    sp.add_argument("--keywords", required=True, help="Comma-separated terms")
    sp.add_argument("--match-type", dest="match_type", default="phrase",
                    choices=["exact", "phrase", "broad"])

    sp = _cmd(sub, "shared-set-keywords", cmd_shared_set_list_keywords,
              "List keywords inside a shared set")
    sp.add_argument("--set", required=True, help="Shared set ID")

    sp = _cmd(sub, "shared-set-remove-keywords", cmd_shared_set_remove_keywords,
              "Remove criteria from a shared set", write=True)
    sp.add_argument("--set", required=True, help="Shared set ID")
    sp.add_argument("--criteria", required=True, help="Criterion IDs CSV")

    sp = _cmd(sub, "shared-set-attach", cmd_shared_set_attach,
              "Attach/detach a shared set to campaigns", write=True)
    sp.add_argument("--set", required=True, help="Shared set ID")
    sp.add_argument("--campaigns", required=True, help="Campaign IDs CSV")
    sp.add_argument("--detach", action="store_true", help="Detach instead of attach")

    sp = _cmd(sub, "customer-negatives-attach", cmd_customer_negatives_attach,
              "Attach an account-negatives shared set to the whole account", write=True)
    sp.add_argument("--set", required=True, help="Shared set ID (type account-negatives)")

    sp = _cmd(sub, "customer-negatives-detach", cmd_customer_negatives_detach,
              "Detach an account-level negatives criterion", write=True)
    sp.add_argument("--criterion", required=True, help="Criterion ID (from attach output)")

    sp = _cmd(sub, "shared-set-remove", cmd_shared_set_remove,
              "Remove a whole shared set (incl. its criteria)", write=True)
    sp.add_argument("--set", required=True, help="Shared set ID")

    # --- Assets ----------------------------------------------------------
    sp = _cmd(sub, "assets", cmd_assets, "List sitelink/callout/snippet assets")
    sp.add_argument("--type", choices=["sitelink", "callout", "snippet"])

    _cmd(sub, "asset-links", cmd_asset_links,
         "Where assets are linked (customer/campaign/ad-group; 3 ops)")

    sp = _cmd(sub, "sitelink-create", cmd_sitelink_create, "Create sitelink assets (JSON)", write=True)
    sp.add_argument("--sitelinks-json", dest="sitelinks_json", required=True,
                    help='[{"text":"Kurz","url":"https://…","desc1":"…","desc2":"…"}]')

    sp = _cmd(sub, "callout-create", cmd_callout_create, "Create callout assets", write=True)
    sp.add_argument("--texts", required=True, help="Pipe-separated, ≤25 chars each")

    sp = _cmd(sub, "snippet-create", cmd_snippet_create,
              "Create a structured snippet asset", write=True)
    sp.add_argument("--header", required=True, help="One of Google's fixed headers (e.g. Courses)")
    sp.add_argument("--values", required=True, help="Pipe-separated, 3–10 × ≤25 chars")

    for name, func, help_text in (
        ("asset-link", cmd_asset_link, "Link assets to customer/campaign/ad group"),
        ("asset-unlink", cmd_asset_unlink, "Unlink assets (assets themselves are undeletable)"),
    ):
        sp = _cmd(sub, name, func, help_text, write=True)
        sp.add_argument("--asset", required=True, help="Asset IDs CSV")
        sp.add_argument("--field-type", dest="field_type", required=True,
                        choices=["sitelink", "callout", "snippet"])
        sp.add_argument("--campaign", help="Campaign ID")
        sp.add_argument("--ad-group", dest="ad_group", help="Ad group ID")
        sp.add_argument("--customer", action="store_true", help="Account level")

    # --- Audiences -------------------------------------------------------
    _cmd(sub, "audiences", cmd_audiences, "List user lists (remarketing audiences)")

    sp = _cmd(sub, "audience-create", cmd_audience_create,
              "Create a rule-based remarketing list (URL contains)", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--url-contains", dest="url_contains", required=True,
                    help="Visitors of URLs containing this string")
    sp.add_argument("--membership-days", dest="membership_days", type=int, default=30,
                    help="Membership life span in days (default 30, max 540)")
    sp.add_argument("--description")

    sp = _cmd(sub, "audiences-attached", cmd_audiences_attached,
              "What audiences are attached where (incl. exclusions)")
    sp.add_argument("--campaign", help="Filter by campaign ID")

    sp = _cmd(sub, "audience-attach", cmd_audience_attach,
              "Attach a user list to a campaign/ad group", write=True)
    sp.add_argument("--list", required=True, help="User list ID")
    sp.add_argument("--campaign", help="Campaign ID")
    sp.add_argument("--ad-group", dest="ad_group", help="Ad group ID")
    sp.add_argument("--mode", choices=["observation", "targeting"],
                    help="observation = bid-only (Google's recommendation for search); "
                         "targeting NARROWS serving to the audience")
    sp.add_argument("--bid-modifier", dest="bid_modifier", type=float,
                    help="e.g. 1.2 = +20 %% bid for the audience")

    sp = _cmd(sub, "audience-exclude", cmd_audience_exclude,
              "Exclude a user list from a campaign", write=True)
    sp.add_argument("--list", required=True, help="User list ID")
    sp.add_argument("--campaign", required=True, help="Campaign ID")

    sp = _cmd(sub, "audience-detach", cmd_audience_detach,
              "Detach an audience criterion", write=True)
    sp.add_argument("--criterion", required=True, help="Criterion ID (from audiences-attached)")
    sp.add_argument("--campaign", help="Campaign ID (campaign-level criterion)")
    sp.add_argument("--ad-group", dest="ad_group", help="Ad group ID (ad-group-level criterion)")

    # --- Targeting -------------------------------------------------------
    sp = _cmd(sub, "geo-suggest", cmd_geo_suggest,
              "Look up geo target constant IDs by name", cid=False)
    sp.add_argument("--name", required=True, help="Location name(s), CSV (e.g. 'Praha,Brno')")
    sp.add_argument("--country", default="CZ", help="Country code filter (default CZ)")
    sp.add_argument("--locale", default="cs", help="Locale for names (default cs)")

    sp = _cmd(sub, "campaign-targeting", cmd_campaign_targeting,
              "List a campaign's targeting criteria")
    sp.add_argument("campaign_id")

    sp = _cmd(sub, "geo-target", cmd_geo_target,
              "Add/exclude/remove campaign geo targeting (+ proximity)", write=True)
    sp.add_argument("campaign_id")
    sp.add_argument("--geo", help="Geo target IDs CSV (from geo-suggest)")
    sp.add_argument("--negative", action="store_true", help="Exclude instead of target")
    sp.add_argument("--proximity", help="'lat,lng,km' radius targeting")
    sp.add_argument("--remove", help="Criterion IDs CSV to remove (from campaign-targeting)")

    sp = _cmd(sub, "language-target", cmd_language_target,
              "Add/remove campaign language targeting", write=True)
    sp.add_argument("campaign_id")
    sp.add_argument("--language", help="Language constant IDs CSV (1021=cs, 1034=sk, 1000=en)")
    sp.add_argument("--remove", help="Criterion IDs CSV to remove")

    sp = _cmd(sub, "schedule-set", cmd_schedule_set,
              "REPLACE a campaign's ad schedule (atomic)", write=True)
    sp.add_argument("campaign_id")
    sp.add_argument("--schedule-json", dest="schedule_json", required=True,
                    help='[{"day":"MONDAY","start":8,"end":20,"bid_modifier":1.1}]; [] = 24/7')

    sp = _cmd(sub, "device-bid", cmd_device_bid,
              "Set a device bid modifier (0 = don't serve)", write=True)
    sp.add_argument("campaign_id")
    sp.add_argument("--device", required=True, help="mobile|desktop|tablet|connected_tv|other")
    sp.add_argument("--modifier", required=True, help="0 or 0.1–10.0 (1.0 = neutral)")

    sp = _cmd(sub, "demographics", cmd_demographics,
              "List ad-group demographic criteria")
    sp.add_argument("--ad-group", dest="ad_group", help="Filter by ad group ID")

    sp = _cmd(sub, "demographic-target", cmd_demographic_target,
              "Add/exclude/remove ad-group demographics", write=True)
    sp.add_argument("--ad-group", dest="ad_group", required=True, help="Ad group ID")
    sp.add_argument("--value", help="CSV: AGE_RANGE_25_34 / MALE / INCOME_RANGE_90_UP …")
    sp.add_argument("--negative", action="store_true", help="Exclude instead of target")
    sp.add_argument("--modifier", type=float, help="Bid modifier (positive targeting only)")
    sp.add_argument("--remove", help="Criterion IDs CSV to remove (from demographics)")

    # --- Labels ----------------------------------------------------------
    _cmd(sub, "labels", cmd_labels, "List labels with IDs")

    sp = _cmd(sub, "label-create", cmd_label_create, "Create a label", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--description")
    sp.add_argument("--color", help="Hex background color, e.g. #FF5B0A")

    sp = _cmd(sub, "label-remove", cmd_label_remove,
              "Remove a label entirely (incl. all assignments)", write=True)
    sp.add_argument("--label", required=True, help="Label ID")

    for name, func, help_text in (
        ("label-assign", cmd_label_assign, "Assign a label to campaign/ad group/ad/keyword"),
        ("label-unassign", cmd_label_unassign, "Remove a label from an entity"),
    ):
        sp = _cmd(sub, name, func, help_text, write=True)
        sp.add_argument("--label", required=True, help="Label ID (from `labels`)")
        sp.add_argument("--campaign", help="Campaign ID")
        sp.add_argument("--ad-group", dest="ad_group", help="Ad group ID")
        sp.add_argument("--ad", help="'adGroupId~adId'")
        sp.add_argument("--keyword", help="'adGroupId~criterionId'")

    # --- Conversions -----------------------------------------------------
    _cmd(sub, "conversions", cmd_conversions, "List conversion actions")

    sp = _cmd(sub, "conversion-create", cmd_conversion_create,
              "Create a WEBPAGE conversion action", write=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--category", required=True, help="PURCHASE / LEAD / SIGNUP / …")
    sp.add_argument("--primary", action="store_true",
                    help="Primary (bidding optimizes to it); default secondary")
    sp.add_argument("--counting", default="one", choices=["one", "many"],
                    help="one = ONE_PER_CLICK (leads), many = MANY_PER_CLICK (purchases)")
    sp.add_argument("--value", type=float, help="Default value (always used)")

    sp = _cmd(sub, "conversion-update", cmd_conversion_update,
              "Update a conversion action", write=True)
    sp.add_argument("conversion_id")
    sp.add_argument("--status", choices=["enabled", "paused", "hidden"])
    sp.add_argument("--primary", choices=["yes", "no"], help="primary_for_goal")
    sp.add_argument("--counting", choices=["one", "many"])
    sp.add_argument("--value", type=float, help="Default value (always used)")

    # --- Recommendations -------------------------------------------------
    _cmd(sub, "recommendations", cmd_recommendations,
         "List Google's recommendations (type, impact)")

    sp = _cmd(sub, "recommendation-apply", cmd_recommendation_apply,
              "Apply recommendation(s)", write=True)
    sp.add_argument("--resource", required=True, help="resource_name(s) CSV from `recommendations`")

    sp = _cmd(sub, "recommendation-dismiss", cmd_recommendation_dismiss,
              "Dismiss recommendation(s)", write=True)
    sp.add_argument("--resource", required=True, help="resource_name(s) CSV from `recommendations`")

    # --- DSA -------------------------------------------------------------
    sp = _cmd(sub, "dsa-setting", cmd_dsa_setting,
              "Set a campaign's DSA setting (domain + language)", write=True)
    sp.add_argument("campaign_id")
    sp.add_argument("--domain", required=True, help="e.g. aifirst.cz")
    sp.add_argument("--language-code", dest="language_code", default="cs")
    sp.add_argument("--supplied-urls-only", dest="supplied_urls_only", action="store_true",
                    help="Serve only from a page feed (not implemented here) ")

    sp = _cmd(sub, "dsa-ad-group-create", cmd_dsa_ad_group_create,
              "Create a DSA ad group (SEARCH_DYNAMIC_ADS)", write=True)
    sp.add_argument("--campaign", required=True, help="DSA-enabled campaign ID")
    sp.add_argument("--name", required=True)
    sp.add_argument("--cpc", type=float, help="Default CPC bid in CZK")

    sp = _cmd(sub, "dsa-create", cmd_dsa_create,
              "Create an Expanded DSA ad (descriptions only)", write=True)
    sp.add_argument("--ad-group", dest="ad_group", required=True, help="DSA ad group ID")
    sp.add_argument("--descriptions", required=True, help="Pipe-separated, 1–2 × ≤90 chars")

    sp = _cmd(sub, "webpage-targets", cmd_webpage_targets,
              "List webpage criteria of a DSA ad group")
    sp.add_argument("--ad-group", dest="ad_group", required=True, help="DSA ad group ID")

    sp = _cmd(sub, "webpage-target-add", cmd_webpage_target_add,
              "Add a webpage criterion (or exclusion) to a DSA ad group", write=True)
    sp.add_argument("--ad-group", dest="ad_group", required=True, help="DSA ad group ID")
    sp.add_argument("--name", required=True, help="Criterion display name")
    sp.add_argument("--conditions", help="'url:blog,title:kurz' (≤3, ANDed; omit = all pages)")
    sp.add_argument("--negative", action="store_true", help="Exclude instead of target")
    sp.add_argument("--cpc", type=float, help="CPC bid in CZK (positive only)")

    sp = _cmd(sub, "webpage-target-remove", cmd_webpage_target_remove,
              "Remove webpage criteria", write=True)
    sp.add_argument("--criteria", required=True, help="'adGroupId~criterionId' CSV")

    # --- PMax (reporting only) -------------------------------------------
    sp = _cmd(sub, "pmax", cmd_pmax, "PMax campaign metrics (reporting only)")
    sp.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    sp.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    sp.add_argument("--channels", action="store_true", help="Split by ad_network_type")

    sp = _cmd(sub, "pmax-search-terms", cmd_pmax_search_terms, "PMax search terms")
    sp.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    sp.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD")
    sp.add_argument("--campaign", help="Filter by campaign ID")

    # --- Experiments ------------------------------------------------------
    _cmd(sub, "experiments", cmd_experiments, "List experiments")

    sp = _cmd(sub, "experiment-create", cmd_experiment_create,
              "Create a SEARCH_CUSTOM experiment + arms (draft campaign is generated)",
              write=True)
    sp.add_argument("--campaign", required=True, help="Base (control) campaign ID")
    sp.add_argument("--name", required=True)
    sp.add_argument("--suffix", default="[experiment]", help="Treatment campaign name suffix")
    sp.add_argument("--traffic-split", dest="traffic_split", default=50,
                    help="%% of traffic for TREATMENT (default 50)")
    sp.add_argument("--start", required=True, help="YYYY-MM-DD (future — ads must clear review)")
    sp.add_argument("--end", required=True, help="YYYY-MM-DD")

    for name, func, help_text in (
        ("experiment-schedule", cmd_experiment_schedule, "Start an experiment (async)"),
        ("experiment-end", cmd_experiment_end, "End an experiment (nothing applied)"),
        ("experiment-promote", cmd_experiment_promote,
         "Promote treatment changes onto the base campaign"),
    ):
        sp = _cmd(sub, name, func, help_text, write=True)
        sp.add_argument("experiment_id")

    sp = _cmd(sub, "experiment-results", cmd_experiment_results,
              "Experiment results: treatment vs control")
    sp.add_argument("experiment_id")

    return p


def main() -> None:
    try:  # don't traceback when piped into head/grep
        from signal import SIG_DFL, SIGPIPE, signal
        signal(SIGPIPE, SIG_DFL)
    except ImportError:  # SIGPIPE doesn't exist on Windows
        pass
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
