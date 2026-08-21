"""Command tests: every write command builds its operations against the REAL
v25 proto types (type/enum/field names validated by construction), defaults to
validate_only, respects the PAUSED-before-REMOVED brake, and listings never
truncate silently."""
from __future__ import annotations

import json

import pytest

from gads.commands import (ads, assets, audiences, budgets, campaigns,
                           conversions, dsa, experiments, groups, keywords,
                           labels, pmax, pulse, recommendations, reporting,
                           research, sharedsets, targeting)

from conftest import ns

CID = "1234567890"


def _ops(call):
    return list(call["request"].operations)


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

def test_campaign_create_is_atomic_paused_search_with_geo_language(recorder):
    campaigns.cmd_campaign_create(ns(name="Test", budget=300, bidding="max_conversions",
                                     target_cpa=None, target_roas=None,
                                     geo="2203", language="1021"))
    call = recorder.last("mutate")
    req = call["request"]
    assert req.validate_only is True
    mops = list(req.mutate_operations)
    assert len(mops) == 4  # budget + campaign + geo + language
    budget = mops[0].campaign_budget_operation.create
    assert budget.amount_micros == 300_000_000 and budget.explicitly_shared is False
    camp = mops[1].campaign_operation.create
    assert camp.status.name == "PAUSED"
    assert camp.advertising_channel_type.name == "SEARCH"
    assert camp.campaign_budget == budget.resource_name
    assert camp.contains_eu_political_advertising.name == "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING"
    assert camp.network_settings.target_content_network is False
    assert mops[2].campaign_criterion_operation.create.location.geo_target_constant.endswith("/2203")
    assert mops[3].campaign_criterion_operation.create.language.language_constant.endswith("/1021")


def test_campaign_create_confirm_writes_and_counts_ops(recorder):
    from gads import api
    campaigns.cmd_campaign_create(ns(name="T", budget=100, bidding="manual_cpc",
                                     target_cpa=None, target_roas=None, geo="", language="",
                                     confirm=True))
    assert recorder.last("mutate")["request"].validate_only is False
    assert api._quota_read(None) == 2  # budget + campaign, no criteria


def test_campaign_create_target_cpa_requires_value(recorder, capsys):
    with pytest.raises(SystemExit):
        campaigns.cmd_campaign_create(ns(name="T", budget=100, bidding="target_cpa",
                                         target_cpa=None, target_roas=None, geo="", language=""))
    assert "--target-cpa" in capsys.readouterr().err
    assert not recorder.calls


def test_campaign_status_pause_is_a_masked_update(recorder):
    campaigns.cmd_campaign_status(ns(campaign_id="42", status="paused", force=False))
    op = _ops(recorder.last("mutate_campaigns"))[0]
    assert op.update.resource_name.endswith("/campaigns/42")
    assert op.update.status.name == "PAUSED"
    assert "status" in list(op.update_mask.paths)


def test_campaign_remove_refused_unless_paused(recorder, row_factory, capsys):
    recorder.rows = [row_factory(**{"campaign.status": 2})]  # 2 = ENABLED
    with pytest.raises(SystemExit):
        campaigns.cmd_campaign_status(ns(campaign_id="42", status="removed", force=False))
    assert "POJISTKA" in capsys.readouterr().err
    assert "mutate_campaigns" not in recorder.methods()


def test_campaign_remove_uses_remove_operation_when_paused(recorder, row_factory):
    recorder.rows = [row_factory(**{"campaign.status": 3})]  # 3 = PAUSED
    campaigns.cmd_campaign_status(ns(campaign_id="42", status="removed", force=False))
    op = _ops(recorder.last("mutate_campaigns"))[0]
    assert op.remove.endswith("/campaigns/42")


def test_campaign_remove_force_skips_the_status_lookup(recorder):
    campaigns.cmd_campaign_status(ns(campaign_id="42", status="removed", force=True))
    assert "search_stream" not in recorder.methods()
    assert _ops(recorder.last("mutate_campaigns"))[0].remove.endswith("/campaigns/42")


def test_bidding_set_target_roas(recorder):
    campaigns.cmd_bidding_set(ns(campaign_id="42", strategy="target_roas",
                                 target_cpa=None, target_roas=2.5))
    op = _ops(recorder.last("mutate_campaigns"))[0]
    assert op.update.target_roas.target_roas == pytest.approx(2.5)
    assert "target_roas.target_roas" in list(op.update_mask.paths)


def test_campaigns_listing_hides_removed_by_default(recorder):
    campaigns.cmd_campaigns(ns(status=None))
    q = recorder.last("search_stream")["request"]["query"]
    assert "campaign.status != 'REMOVED'" in q and "LIMIT" not in q


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

def test_budget_set_updates_the_campaigns_budget_and_warns_if_shared(recorder, row_factory, capsys):
    recorder.rows = [row_factory(**{"campaign.id": 42, "campaign.name": "X",
                                    "campaign_budget.resource_name": f"customers/{CID}/campaignBudgets/7",
                                    "campaign_budget.amount_micros": 100_000_000,
                                    "campaign_budget.explicitly_shared": True})]
    budgets.cmd_budget_set(ns(campaign_id="42", amount=350))
    op = _ops(recorder.last("mutate_campaign_budgets"))[0]
    assert op.update.resource_name.endswith("/campaignBudgets/7")
    assert op.update.amount_micros == 350_000_000
    assert "SDÍLENÉM" in capsys.readouterr().out


def test_budget_create_is_explicitly_shared(recorder):
    budgets.cmd_budget_create(ns(name="Shared", amount=1000))
    op = _ops(recorder.last("mutate_campaign_budgets"))[0]
    assert op.create.explicitly_shared is True and op.create.amount_micros == 1_000_000_000


def test_budget_assign_points_campaigns_at_budget(recorder):
    budgets.cmd_budget_assign(ns(budget_id="7", campaigns="1,2"))
    ops = _ops(recorder.last("mutate_campaigns"))
    assert len(ops) == 2 and all(o.update.campaign_budget.endswith("/campaignBudgets/7") for o in ops)
    assert "campaign_budget" in list(ops[0].update_mask.paths)


# ---------------------------------------------------------------------------
# Ad groups, ads
# ---------------------------------------------------------------------------

def test_ad_group_create_search_standard_with_cpc(recorder):
    groups.cmd_ad_group_create(ns(campaign="42", name="AG", cpc=12.5))
    op = _ops(recorder.last("mutate_ad_groups"))[0]
    assert op.create.type_.name == "SEARCH_STANDARD"
    assert op.create.cpc_bid_micros == 12_500_000
    assert op.create.campaign.endswith("/campaigns/42")


def test_rsa_create_lint_blocks_before_any_api_call(recorder, capsys):
    with pytest.raises(SystemExit):
        ads.cmd_rsa_create(ns(ad_group="1", headlines="Jen|Dva", descriptions="a|b",
                              final_url="https://x.cz", path1=None, path2=None))
    assert "3–15 headlines" in capsys.readouterr().err
    assert not recorder.calls


def test_rsa_create_builds_pinned_assets_and_paths(recorder):
    ads.cmd_rsa_create(ns(ad_group="1",
                          headlines="AI First @H1|Kurz vibe codingu|Začni dnes",
                          descriptions="Popis jedna @D1|Popis dva",
                          final_url="https://aifirst.cz", path1="kurz", path2=None))
    call = recorder.last("mutate_ad_group_ads")
    assert call["request"].validate_only is True
    aga = _ops(call)[0].create
    rsa = aga.ad.responsive_search_ad
    assert [h.text for h in rsa.headlines] == ["AI First", "Kurz vibe codingu", "Začni dnes"]
    assert rsa.headlines[0].pinned_field.name == "HEADLINE_1"
    assert rsa.headlines[1].pinned_field.name == "UNSPECIFIED"
    assert rsa.descriptions[0].pinned_field.name == "DESCRIPTION_1"
    assert rsa.path1 == "kurz" and list(aga.ad.final_urls) == ["https://aifirst.cz"]
    assert aga.ad_group.endswith("/adGroups/1")


def test_rsa_create_rejects_wrong_pin_target(recorder, capsys):
    with pytest.raises(SystemExit):
        ads.cmd_rsa_create(ns(ad_group="1", headlines="A @D1|B|C", descriptions="x|y",
                              final_url="https://x.cz", path1=None, path2=None))
    assert "H1/H2/H3" in capsys.readouterr().err


def test_ad_remove_brake_and_remove_operation(recorder, row_factory, capsys):
    recorder.rows = [row_factory(**{"ad_group_ad.status": 2})]  # ENABLED
    with pytest.raises(SystemExit):
        ads.cmd_ad_status(ns(ad_group_id="1", ad_id="9", status="removed", force=False))
    assert "POJISTKA" in capsys.readouterr().err
    recorder.rows = [row_factory(**{"ad_group_ad.status": 3})]  # PAUSED
    ads.cmd_ad_status(ns(ad_group_id="1", ad_id="9", status="removed", force=False))
    assert _ops(recorder.last("mutate_ad_group_ads"))[0].remove.endswith("/adGroupAds/1~9")


def test_ad_update_url_uses_ad_service(recorder):
    ads.cmd_ad_update_url(ns(ad_id="9", final_url="https://new.cz"))
    call = recorder.last("mutate_ads")
    assert call["service"] == "AdService"
    op = _ops(call)[0]
    assert list(op.update.final_urls) == ["https://new.cz"] and "final_urls" in list(op.update_mask.paths)


def test_ad_policy_only_problems_filters_in_gaql(recorder):
    ads.cmd_ad_policy(ns(ad_group=None, campaign=None, only_problems=True))
    assert "approval_status != 'APPROVED'" in recorder.last("search_stream")["request"]["query"]


# ---------------------------------------------------------------------------
# Keywords & negatives
# ---------------------------------------------------------------------------

def test_keyword_add_builds_criteria_with_match_types_and_cpc(recorder):
    keywords.cmd_keyword_add(ns(ad_group="1", keywords_json=json.dumps([
        {"text": "kurz ai", "match_type": "phrase", "cpc": 25},
        {"text": "ai školení", "match_type": "exact"},
    ])))
    ops = _ops(recorder.last("mutate_ad_group_criteria"))
    assert ops[0].create.keyword.text == "kurz ai"
    assert ops[0].create.keyword.match_type.name == "PHRASE" and ops[0].create.cpc_bid_micros == 25_000_000
    assert ops[1].create.keyword.match_type.name == "EXACT" and ops[1].create.cpc_bid_micros == 0


def test_keyword_add_invalid_json_is_clean(recorder, capsys):
    with pytest.raises(SystemExit):
        keywords.cmd_keyword_add(ns(ad_group="1", keywords_json="[{oops"))
    assert "Neplatný JSON" in capsys.readouterr().err and not recorder.calls


def test_negative_add_campaign_level_and_ad_group_level(recorder):
    keywords.cmd_negative_add(ns(ad_group=None, campaign="42", keywords="zdarma, práce",
                                 match_type="phrase"))
    call = recorder.last("mutate_campaign_criteria")
    ops = _ops(call)
    assert [o.create.keyword.text for o in ops] == ["zdarma", "práce"]
    assert all(o.create.negative for o in ops)
    keywords.cmd_negative_add(ns(ad_group="1", campaign=None, keywords="free", match_type="exact"))
    assert _ops(recorder.last("mutate_ad_group_criteria"))[0].create.keyword.match_type.name == "EXACT"


def test_negative_add_requires_a_scope(recorder, capsys):
    with pytest.raises(SystemExit):
        keywords.cmd_negative_add(ns(ad_group=None, campaign=None, keywords="x", match_type="phrase"))
    assert "--ad-group NEBO --campaign" in capsys.readouterr().err


def test_keyword_remove_builds_composite_resource_names(recorder):
    keywords.cmd_keyword_remove(ns(criteria="1~100, 1~101"))
    ops = _ops(recorder.last("mutate_ad_group_criteria"))
    assert [o.remove for o in ops] == [f"customers/{CID}/adGroupCriteria/1~100",
                                       f"customers/{CID}/adGroupCriteria/1~101"]


# ---------------------------------------------------------------------------
# Shared sets
# ---------------------------------------------------------------------------

def test_shared_set_lifecycle_ops(recorder):
    sharedsets.cmd_shared_set_create(ns(name="Junk", type="account-negatives"))
    assert _ops(recorder.last("mutate_shared_sets"))[0].create.type_.name == "ACCOUNT_LEVEL_NEGATIVE_KEYWORDS"
    sharedsets.cmd_shared_set_add(ns(set="5", keywords="a,b", match_type="broad"))
    ops = _ops(recorder.last("mutate_shared_criteria"))
    assert ops[0].create.shared_set.endswith("/sharedSets/5") and ops[0].create.keyword.match_type.name == "BROAD"
    sharedsets.cmd_shared_set_remove_keywords(ns(set="5", criteria="11,12"))
    assert _ops(recorder.last("mutate_shared_criteria"))[0].remove == f"customers/{CID}/sharedCriteria/5~11"
    sharedsets.cmd_shared_set_attach(ns(set="5", campaigns="1,2", detach=False))
    assert _ops(recorder.last("mutate_campaign_shared_sets"))[1].create.campaign.endswith("/campaigns/2")
    sharedsets.cmd_shared_set_attach(ns(set="5", campaigns="1", detach=True))
    assert _ops(recorder.last("mutate_campaign_shared_sets"))[0].remove == f"customers/{CID}/campaignSharedSets/1~5"
    sharedsets.cmd_customer_negatives_attach(ns(set="5"))
    crit = _ops(recorder.last("mutate_customer_negative_criteria"))[0].create
    assert crit.negative_keyword_list.shared_set.endswith("/sharedSets/5")


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

def test_sitelink_create_validates_descriptions_pairing(recorder, capsys):
    with pytest.raises(SystemExit):
        assets.cmd_sitelink_create(ns(sitelinks_json=json.dumps(
            [{"text": "Kurz", "url": "https://x.cz", "desc1": "jen jedna"}])))
    assert "desc1 a desc2" in capsys.readouterr().err and not recorder.calls


def test_sitelink_create_builds_assets(recorder):
    assets.cmd_sitelink_create(ns(sitelinks_json=json.dumps([
        {"text": "Kurz", "url": "https://x.cz/kurz", "desc1": "Popis 1", "desc2": "Popis 2"},
        {"text": "Blog", "url": "https://x.cz/blog"},
    ])))
    ops = _ops(recorder.last("mutate_assets"))
    assert ops[0].create.sitelink_asset.link_text == "Kurz"
    assert ops[0].create.sitelink_asset.description2 == "Popis 2"
    assert list(ops[1].create.final_urls) == ["https://x.cz/blog"]


def test_callout_lint_length(recorder, capsys):
    with pytest.raises(SystemExit):
        assets.cmd_callout_create(ns(texts="Tohle je moc dlouhý callout text přes limit"))
    assert "max 25" in capsys.readouterr().err


def test_snippet_header_must_be_official(recorder, capsys):
    with pytest.raises(SystemExit):
        assets.cmd_snippet_create(ns(header="Kurzy", values="a|b|c"))
    assert "Courses" in capsys.readouterr().err
    assets.cmd_snippet_create(ns(header="Courses", values="AI|Vibe coding|Marketing"))
    a = _ops(recorder.last("mutate_assets"))[0].create.structured_snippet_asset
    assert a.header == "Courses" and list(a.values) == ["AI", "Vibe coding", "Marketing"]


def test_asset_link_and_unlink_per_level(recorder):
    assets.cmd_asset_link(ns(asset="10,11", field_type="sitelink", campaign="42",
                             ad_group=None, customer=False))
    call = recorder.last("mutate_campaign_assets")
    ops = _ops(call)
    assert ops[0].create.field_type.name == "SITELINK" and ops[0].create.campaign.endswith("/campaigns/42")
    assets.cmd_asset_unlink(ns(asset="10", field_type="callout", campaign=None,
                               ad_group="7", customer=False))
    assert _ops(recorder.last("mutate_ad_group_assets"))[0].remove == f"customers/{CID}/adGroupAssets/7~10~CALLOUT"
    assets.cmd_asset_unlink(ns(asset="10", field_type="snippet", campaign=None,
                               ad_group=None, customer=True))
    assert _ops(recorder.last("mutate_customer_assets"))[0].remove == f"customers/{CID}/customerAssets/10~STRUCTURED_SNIPPET"


# ---------------------------------------------------------------------------
# Audiences
# ---------------------------------------------------------------------------

def test_audience_create_builds_flexible_rule_list(recorder):
    audiences.cmd_audience_create(ns(name="Visitors", url_contains="aifirst.cz",
                                     membership_days=30, description=None))
    ul = _ops(recorder.last("mutate_user_lists"))[0].create
    assert ul.membership_life_span == 30
    flex = ul.rule_based_user_list.flexible_rule_user_list
    item = flex.inclusive_operands[0].rule.rule_item_groups[0].rule_items[0]
    assert item.name == "url__" and item.string_rule_item.value == "aifirst.cz"
    assert item.string_rule_item.operator.name == "CONTAINS"
    assert ul.rule_based_user_list.prepopulation_status.name == "REQUESTED"


def test_audience_attach_observation_flips_targeting_setting(recorder, row_factory, fake_client):
    recorder.rows = [row_factory()]
    audiences.cmd_audience_attach(ns(list="555", campaign="42", ad_group=None,
                                     mode="observation", bid_modifier=1.2))
    crit = _ops(recorder.last("mutate_campaign_criteria"))[0].create
    assert crit.user_list.user_list.endswith("/userLists/555") and crit.bid_modifier == pytest.approx(1.2)
    camp = _ops(recorder.last("mutate_campaigns"))[0].update
    tr = list(camp.targeting_setting.target_restrictions)
    assert len(tr) == 1 and tr[0].targeting_dimension.name == "AUDIENCE" and tr[0].bid_only is True


def test_audience_attach_needs_exactly_one_scope(recorder, capsys):
    with pytest.raises(SystemExit):
        audiences.cmd_audience_attach(ns(list="1", campaign="1", ad_group="2", mode=None, bid_modifier=None))
    assert "NEBO" in capsys.readouterr().err


def test_audience_exclude_is_negative_campaign_criterion(recorder):
    audiences.cmd_audience_exclude(ns(list="555", campaign="42"))
    crit = _ops(recorder.last("mutate_campaign_criteria"))[0].create
    assert crit.negative is True and crit.user_list.user_list.endswith("/userLists/555")


# ---------------------------------------------------------------------------
# Targeting
# ---------------------------------------------------------------------------

def test_geo_target_negative_proximity_and_remove(recorder):
    targeting.cmd_geo_target(ns(campaign_id="42", geo="1003803", negative=True,
                                proximity="50.08,14.43,20", remove="999"))
    ops = _ops(recorder.last("mutate_campaign_criteria"))
    assert ops[0].create.negative is True and ops[0].create.location.geo_target_constant.endswith("/1003803")
    prox = ops[1].create.proximity
    assert prox.geo_point.latitude_in_micro_degrees == 50_080_000
    assert prox.radius == pytest.approx(20) and prox.radius_units.name == "KILOMETERS"
    assert ops[2].remove == f"customers/{CID}/campaignCriteria/42~999"


def test_schedule_set_replaces_atomically(recorder, row_factory):
    recorder.rows = [row_factory(**{"campaign_criterion.criterion_id": 301}),
                     row_factory(**{"campaign_criterion.criterion_id": 302})]
    targeting.cmd_schedule_set(ns(campaign_id="42", schedule_json=json.dumps(
        [{"day": "MONDAY", "start": 8, "end": 20, "bid_modifier": 1.1}])))
    ops = _ops(recorder.last("mutate_campaign_criteria"))
    assert [o.remove for o in ops[:2]] == [f"customers/{CID}/campaignCriteria/42~301",
                                           f"customers/{CID}/campaignCriteria/42~302"]
    sched = ops[2].create.ad_schedule
    assert sched.day_of_week.name == "MONDAY" and sched.start_hour == 8 and sched.end_hour == 20
    assert ops[2].create.bid_modifier == pytest.approx(1.1)


def test_schedule_set_rejects_unknown_day(recorder, capsys):
    with pytest.raises(SystemExit):
        targeting.cmd_schedule_set(ns(campaign_id="42", schedule_json='[{"day":"PONDELI"}]'))
    assert "Neznámý den" in capsys.readouterr().err


def test_device_bid_updates_existing_criterion(recorder, row_factory):
    recorder.rows = [row_factory(**{"campaign_criterion.criterion_id": 30001,
                                    "campaign_criterion.device.type_": 2})]  # MOBILE
    targeting.cmd_device_bid(ns(campaign_id="42", device="mobile", modifier="0"))
    op = _ops(recorder.last("mutate_campaign_criteria"))[0]
    assert op.update.resource_name == f"customers/{CID}/campaignCriteria/42~30001"
    assert op.update.bid_modifier == 0 and "bid_modifier" in list(op.update_mask.paths)


def test_device_bid_range_check(recorder, capsys):
    with pytest.raises(SystemExit):
        targeting.cmd_device_bid(ns(campaign_id="42", device="mobile", modifier="15"))
    assert "0.1–10.0" in capsys.readouterr().err


def test_demographic_target_values_and_exclusion(recorder, capsys):
    targeting.cmd_demographic_target(ns(ad_group="7", value="AGE_RANGE_25_34,FEMALE",
                                        negative=True, modifier=None, remove=None))
    ops = _ops(recorder.last("mutate_ad_group_criteria"))
    assert ops[0].create.age_range.type_.name == "AGE_RANGE_25_34" and ops[0].create.negative
    assert ops[1].create.gender.type_.name == "FEMALE"
    with pytest.raises(SystemExit):
        targeting.cmd_demographic_target(ns(ad_group="7", value="TEENS", negative=False,
                                            modifier=None, remove=None))
    assert "Neznámá hodnota" in capsys.readouterr().err


def test_geo_suggest_uses_planning_service(recorder):
    targeting.cmd_geo_suggest(ns(name="Praha,Brno", country="CZ", locale="cs", account=None))
    call = recorder.last("suggest_geo_target_constants")
    assert list(call["request"].location_names.names) == ["Praha", "Brno"]
    assert call["request"].country_code == "CZ"


# ---------------------------------------------------------------------------
# Labels, conversions, recommendations
# ---------------------------------------------------------------------------

def test_label_assign_to_keyword_and_unassign_from_ad(recorder):
    labels.cmd_label_assign(ns(label="3", campaign=None, ad_group=None, ad=None, keyword="7~88"))
    call = recorder.last("mutate_ad_group_criterion_labels")
    assert _ops(call)[0].create.ad_group_criterion == f"customers/{CID}/adGroupCriteria/7~88"
    labels.cmd_label_unassign(ns(label="3", campaign=None, ad_group=None, ad="7~99", keyword=None))
    assert _ops(recorder.last("mutate_ad_group_ad_labels"))[0].remove == f"customers/{CID}/adGroupAdLabels/7~99~3"


def test_conversion_create_validates_category_and_builds_action(recorder, capsys):
    with pytest.raises(SystemExit):
        conversions.cmd_conversion_create(ns(name="X", category="LEAD", primary=True,
                                             counting="one", value=None))
    assert "SUBMIT_LEAD_FORM" in capsys.readouterr().err
    conversions.cmd_conversion_create(ns(name="Nákup", category="purchase", primary=True,
                                         counting="many", value=1990))
    ca = _ops(recorder.last("mutate_conversion_actions"))[0].create
    assert ca.type_.name == "WEBPAGE" and ca.category.name == "PURCHASE" and ca.primary_for_goal
    assert ca.counting_type.name == "MANY_PER_CLICK"
    assert ca.value_settings.default_value == pytest.approx(1990) and ca.value_settings.always_use_default_value


def test_conversion_update_requires_a_change(recorder, capsys):
    with pytest.raises(SystemExit):
        conversions.cmd_conversion_update(ns(conversion_id="1", status=None, primary=None,
                                             counting=None, value=None))
    assert "aspoň jednu změnu" in capsys.readouterr().err
    conversions.cmd_conversion_update(ns(conversion_id="1", status=None, primary="no",
                                         counting=None, value=None))
    op = _ops(recorder.last("mutate_conversion_actions"))[0]
    assert op.update.primary_for_goal is False and "primary_for_goal" in list(op.update_mask.paths)


def test_recommendation_apply_dry_run_makes_no_call(recorder, capsys):
    recommendations.cmd_recommendation_apply(ns(resource=f"customers/{CID}/recommendations/abc"))
    assert not recorder.calls and "jen plán" in capsys.readouterr().out
    recommendations.cmd_recommendation_apply(ns(resource=f"customers/{CID}/recommendations/abc",
                                                confirm=True))
    call = recorder.last("apply_recommendation")
    assert list(call["request"].operations)[0].resource_name.endswith("/abc")


# ---------------------------------------------------------------------------
# DSA
# ---------------------------------------------------------------------------

def test_dsa_setting_and_ad_group_and_ad(recorder, capsys):
    dsa.cmd_dsa_setting(ns(campaign_id="42", domain="aifirst.cz", language_code="cs",
                           supplied_urls_only=False))
    op = _ops(recorder.last("mutate_campaigns"))[0]
    assert op.update.dynamic_search_ads_setting.domain_name == "aifirst.cz"
    assert "dynamic_search_ads_setting.domain_name" in list(op.update_mask.paths)
    dsa.cmd_dsa_ad_group_create(ns(campaign="42", name="DSA", cpc=None))
    assert _ops(recorder.last("mutate_ad_groups"))[0].create.type_.name == "SEARCH_DYNAMIC_ADS"
    with pytest.raises(SystemExit):
        dsa.cmd_dsa_create(ns(ad_group="7", descriptions="a|b|c"))
    assert "1–2 descriptions" in capsys.readouterr().err
    dsa.cmd_dsa_create(ns(ad_group="7", descriptions="Popis jedna|Popis dva"))
    ad = _ops(recorder.last("mutate_ad_group_ads"))[0].create.ad.expanded_dynamic_search_ad
    assert ad.description == "Popis jedna" and ad.description2 == "Popis dva"


def test_webpage_target_add_conditions(recorder, capsys):
    dsa.cmd_webpage_target_add(ns(ad_group="7", name="Blog", conditions="url:blog,title:kurz",
                                  negative=False, cpc=8))
    crit = _ops(recorder.last("mutate_ad_group_criteria"))[0].create
    conds = list(crit.webpage.conditions)
    assert conds[0].operand.name == "URL" and conds[0].argument == "blog"
    assert conds[1].operand.name == "PAGE_TITLE" and crit.cpc_bid_micros == 8_000_000
    with pytest.raises(SystemExit):
        dsa.cmd_webpage_target_add(ns(ad_group="7", name="X", conditions="url:a,url:b,url:c,url:d",
                                      negative=False, cpc=None))
    assert "Max 3" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------

def test_experiment_create_dry_run_makes_no_call_confirm_builds_two_arms(recorder):
    args = ns(campaign="42", name="Exp", suffix="[exp]", traffic_split="40",
              start="2026-09-01", end="2026-09-30")
    experiments.cmd_experiment_create(args)
    assert not recorder.calls
    args.confirm = True
    experiments.cmd_experiment_create(args)
    exp = _ops(recorder.last("mutate_experiments"))[0].create
    assert exp.type_.name == "SEARCH_CUSTOM" and exp.status.name == "SETUP"
    arms = _ops(recorder.last("mutate_experiment_arms"))
    assert arms[0].create.control is True and arms[0].create.traffic_split == 60
    assert arms[1].create.control is False and arms[1].create.traffic_split == 40
    assert recorder.last("mutate_experiment_arms")["request"].response_content_type.name == "MUTABLE_RESOURCE"


def test_experiment_end_in_setup_removes_instead(recorder, row_factory, fake_client):
    recorder.rows = [row_factory(**{"experiment.status": fake_client.enums.ExperimentStatusEnum.SETUP})]
    experiments.cmd_experiment_end(ns(experiment_id="5", confirm=True))
    assert _ops(recorder.last("mutate_experiments"))[0].remove.endswith("/experiments/5")
    assert "end_experiment" not in recorder.methods()


# ---------------------------------------------------------------------------
# Listings & reports — never truncate silently
# ---------------------------------------------------------------------------

def test_pmax_search_terms_has_no_hardcoded_limit(recorder, row_factory, capsys):
    recorder.rows = [row_factory(**{"campaign_search_term_view.search_term": f"t{i}",
                                    "metrics.clicks": i}) for i in range(5)]
    pmax.cmd_pmax_search_terms(ns(date_from="2026-08-01", date_to="2026-08-20",
                                  campaign=None, limit=None, json=True))
    assert "LIMIT" not in recorder.last("search_stream")["request"]["query"]
    assert len(json.loads(capsys.readouterr().out)) == 5
    pmax.cmd_pmax_search_terms(ns(date_from="2026-08-01", date_to="2026-08-20",
                                  campaign=None, limit=2, json=True))
    captured = capsys.readouterr()
    assert len(json.loads(captured.out)) == 2 and "prvních 2 z 5" in captured.err


def test_changes_warns_when_result_hits_the_limit(recorder, row_factory, capsys):
    recorder.rows = [row_factory() for _ in range(3)]
    reporting.cmd_changes(ns(days=None, sweep=False, limit=3, json=True))
    q = recorder.last("search_stream")["request"]["query"]
    assert "LIMIT 3" in q and "change_event" in q
    assert "useknutá" in capsys.readouterr().err


def test_changes_rejects_windows_beyond_api_limits(recorder, capsys):
    with pytest.raises(SystemExit):
        reporting.cmd_changes(ns(days=30, sweep=False, limit=None))
    assert "posledních 30 dní" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        reporting.cmd_changes(ns(days=90, sweep=True, limit=None))


def test_keywords_research_notes_when_trimming(recorder, capsys):
    research.cmd_keywords_research(ns(seed="kurz ai", language="1021", geo="2203", limit=10))
    call = recorder.last("generate_keyword_ideas")
    assert list(call["request"].keyword_seed.keywords) == ["kurz ai"]
    assert call["request"].language.endswith("/1021")


def test_pulse_is_five_queries_by_default_four_with_no_compare(recorder):
    pulse.cmd_pulse(ns(days=None, date_from=None, date_to=None, no_compare=False, json=True))
    assert recorder.methods().count("search_stream") == 5
    recorder.calls.clear()
    pulse.cmd_pulse(ns(days=None, date_from=None, date_to=None, no_compare=True, json=True))
    assert recorder.methods().count("search_stream") == 4


def test_listings_have_no_hardcoded_limit_anywhere(recorder):
    """Every listing command issues unbounded GAQL (search_stream pages itself);
    the only LIMITs allowed are the API-mandated ones in `changes`."""
    for fn, args in (
        (campaigns.cmd_campaigns, ns(status=None)),
        (groups.cmd_ad_groups, ns(campaign=None)),
        (ads.cmd_ads, ns(ad_group=None, campaign=None)),
        (keywords.cmd_keywords, ns(ad_group=None, campaign=None)),
        (budgets.cmd_budgets, ns()),
        (assets.cmd_assets, ns(type=None)),
        (audiences.cmd_audiences, ns()),
        (sharedsets.cmd_shared_sets, ns()),
        (labels.cmd_labels, ns()),
        (conversions.cmd_conversions, ns()),
        (experiments.cmd_experiments, ns()),
        (research.cmd_search_terms, ns(date_from="2026-08-01", date_to="2026-08-20")),
        (reporting.cmd_report, ns(entity="keyword", date_from="2026-08-01", date_to="2026-08-20")),
    ):
        recorder.calls.clear()
        fn(args)
        for call in recorder.calls:
            if call["method"] == "search_stream":
                assert "LIMIT" not in call["request"]["query"], fn.__name__


# ---------------------------------------------------------------------------
# Regression: updates to DEFAULT values must not vanish from the field mask
# (protobuf_helpers.field_mask diffs values, not presence → silent API no-op)
# ---------------------------------------------------------------------------

def test_bidding_set_max_conversions_without_target_is_in_the_mask(recorder):
    campaigns.cmd_bidding_set(ns(campaign_id="42", strategy="max_conversions",
                                 target_cpa=None, target_roas=None))
    op = _ops(recorder.last("mutate_campaigns"))[0]
    assert "maximize_conversions.target_cpa_micros" in list(op.update_mask.paths)
    assert "maximize_conversions" not in list(op.update_mask.paths)  # bare empty message = FIELD_HAS_SUBFIELDS
    assert op.update._pb.WhichOneof("campaign_bidding_strategy") == "maximize_conversions"


def test_bidding_set_manual_cpc_is_in_the_mask(recorder):
    campaigns.cmd_bidding_set(ns(campaign_id="42", strategy="manual_cpc",
                                 target_cpa=None, target_roas=None))
    op = _ops(recorder.last("mutate_campaigns"))[0]
    assert "manual_cpc.enhanced_cpc_enabled" in list(op.update_mask.paths)


def test_device_bid_zero_is_in_the_mask(recorder, row_factory, fake_client):
    recorder.rows = [row_factory(**{"campaign_criterion.criterion_id": 30001,
                                    "campaign_criterion.device.type_": fake_client.enums.DeviceEnum.MOBILE})]
    targeting.cmd_device_bid(ns(campaign_id="42", device="mobile", modifier="0"))
    op = _ops(recorder.last("mutate_campaign_criteria"))[0]
    assert op.update.bid_modifier == 0 and "bid_modifier" in list(op.update_mask.paths)


def test_conversion_update_primary_no_is_in_the_mask(recorder):
    conversions.cmd_conversion_update(ns(conversion_id="1", status=None, primary="no",
                                         counting=None, value=None))
    op = _ops(recorder.last("mutate_conversion_actions"))[0]
    assert op.update.primary_for_goal is False and "primary_for_goal" in list(op.update_mask.paths)


def test_field_mask_does_not_duplicate_parent_of_nested_paths(fake_client):
    from gads.api import _field_mask
    ca = fake_client.get_type("ConversionAction")
    ca.resource_name = "x"
    ca.value_settings.default_value = 0
    ca.value_settings.always_use_default_value = True
    paths = list(_field_mask(fake_client, ca).paths)
    assert "value_settings.always_use_default_value" in paths
    assert "value_settings" not in paths  # nested path wins over the parent


def test_bidding_set_max_conversion_value_without_target_names_a_subfield(recorder):
    campaigns.cmd_bidding_set(ns(campaign_id="42", strategy="max_conversion_value",
                                 target_cpa=None, target_roas=None))
    paths = list(_ops(recorder.last("mutate_campaigns"))[0].update_mask.paths)
    assert "maximize_conversion_value.target_roas" in paths and "maximize_conversion_value" not in paths


def test_field_mask_never_names_a_bare_empty_message(fake_client):
    """Generic fallback: an empty set submessage with no explicit leaf mapping
    gets its first scalar subfield named (the API rejects the bare parent)."""
    from gads.api import _field_mask
    camp = fake_client.get_type("Campaign")
    camp.resource_name = "x"
    camp._pb.target_spend.SetInParent()   # empty TargetSpend, not in the explicit map
    paths = list(_field_mask(fake_client, camp).paths)
    assert "target_spend" not in paths and "target_spend.target_spend_micros" in paths
