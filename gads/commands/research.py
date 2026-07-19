"""Research: Keyword Planner ideas, search terms."""
from __future__ import annotations

import argparse

from gads.api import (_clean_id, _execute_with_retry, _get_client,
                      _quota_guard, _run_query, _track_ops)
from gads.formatting import _micros, _output_json, _row_to_dict


def cmd_keywords_research(args: argparse.Namespace) -> None:
    """Keyword Planner — generate keyword ideas with volume / competition / CPC.

    NOTE: planning services are limited to 1 QPS — run requests sequentially.
    """
    client = _get_client(args.account)
    svc = client.get_service("KeywordPlanIdeaService")
    gtc_service = client.get_service("GoogleAdsService")

    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = _clean_id(args.customer_id)
    request.language = gtc_service.language_constant_path(args.language)
    request.geo_target_constants.append(
        gtc_service.geo_target_constant_path(args.geo)
    )
    request.keyword_plan_network = (
        client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    )
    seeds = [s.strip() for s in args.seed.split(",") if s.strip()]
    request.keyword_seed.keywords.extend(seeds)

    # GenerateKeywordIdeas is a non-Get/Mutate/Search call = 1 operation.
    _quota_guard(args.account, 1)
    response = _execute_with_retry(
        lambda: svc.generate_keyword_ideas(request=request),
        what=f"keyword-ideas {request.customer_id}",
    )
    if response is None:
        return

    ideas = []
    for idea in response:
        m = idea.keyword_idea_metrics
        ideas.append({
            "keyword": idea.text,
            "avg_monthly_searches": m.avg_monthly_searches,
            "competition": m.competition.name if hasattr(m.competition, "name") else str(m.competition),
            "low_top_of_page_bid": _micros(m.low_top_of_page_bid_micros),
            "high_top_of_page_bid": _micros(m.high_top_of_page_bid_micros),
        })
    _track_ops(args.account, 1)  # 1 op per generate request, not per idea
    ideas.sort(key=lambda k: k["avg_monthly_searches"], reverse=True)
    if args.limit:
        ideas = ideas[: args.limit]

    if args.json:
        _output_json(ideas)
        return
    if not ideas:
        print("No keyword ideas returned.")
        return
    print(f"{'keyword':<40}  {'searches/mo':>11}  {'comp':<8}  {'CPC low–high'}")
    for k in ideas:
        print(f"{k['keyword'][:40]:<40}  {k['avg_monthly_searches']:>11,}  "
              f"{k['competition']:<8}  {k['low_top_of_page_bid']:.2f}–{k['high_top_of_page_bid']:.2f}")


def cmd_search_terms(args: argparse.Namespace) -> None:
    """Actual search queries that triggered ads — the source for negative keywords."""
    client = _get_client(args.account)
    gaql = f"""
        SELECT search_term_view.search_term, segments.search_term_match_type,
               campaign.name, ad_group.name,
               metrics.impressions, metrics.clicks, metrics.cost_micros,
               metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{args.date_from}' AND '{args.date_to}'
        ORDER BY metrics.cost_micros DESC
    """
    rows = _run_query(client, _clean_id(args.customer_id), gaql, args.account)
    out = [_row_to_dict(r) for r in rows]
    if args.json:
        _output_json(out)
        return
    if not out:
        print("No search terms for the given range.")
        return
    for r in out:
        m = r.get("metrics", {})
        term = r.get("searchTermView", {}).get("searchTerm", "?")
        print(f"{term[:45]:<45}  impr {int(m.get('impressions', 0)):>7}  "
              f"clicks {int(m.get('clicks', 0)):>5}  "
              f"cost {_micros(int(m.get('costMicros', 0))):>9,.0f}  "
              f"conv {float(m.get('conversions', 0)):>6.1f}")
