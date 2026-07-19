# Google Ads — Campaign Structure

How to structure search campaigns and choose budgets/bidding.

## Hierarchy

```
Account (customer)
├── Conversion actions (primary = what bidding optimizes to)
├── Assets (sitelinks/callouts/snippets — linkable at all levels)
├── Shared sets (negative keyword lists) + account-level negatives
├── Audiences (user lists)
└── Campaign (SEARCH)
    ├── Budget (daily; own or shared)
    ├── Bidding strategy (campaign-level)
    ├── Targeting: geo, language, ad schedule, device modifiers
    ├── Negative keywords (campaign level) + shared sets attached
    ├── Audience criteria (targeting/observation/exclusion)
    └── Ad group (one tight theme each)
        ├── Keywords (match type per keyword)
        ├── Negative keywords (ad-group level)
        ├── Demographics (age/gender/income incl. exclusions)
        └── RSA — 2–3 per group
```

## Ad-group granularity — one tight theme per group

Split ad groups by a single, specific theme/intent so ad and keywords match tightly. Tighter theme → the ad can echo the exact query → higher relevance and Quality Score. Not one giant "everything" group.

## Naming convention — be consistent

Pick a scheme and stick to it (e.g. `SEA_<Theme>[_<year/variant>]`) — you'll read the account at a glance.

## Targeting — never launch worldwide

A SEARCH campaign with no geo/language criteria serves **worldwide, all languages**. The CLI's `campaign-create` therefore defaults to a geo + language (configure per market); verify with `campaign-targeting` before enabling. Add ad schedule / device modifiers only with data to justify them.

## Budget

- Daily budget on the campaign's budget object (`budget-set`). Google may spend up to ~2× the daily amount on strong days but averages out over the month (30.4× monthly cap).
- Start conservative; scale on campaigns/keywords that prove ROAS.
- Profitable campaign with high "lost impression share (budget)" → raising budget is usually the highest-ROI move (pulse flags this).
- Shared budgets (`budget-create` + `budget-assign`) pool a daily amount across campaigns. One-way street: a shared budget can never become non-shared.

## Bidding strategy — selection guide

| Strategy (CLI value) | Optimizes for | Use when |
|---|---|---|
| `manual_cpc` | clicks (you set bids) | new campaign with no conversion data, or full manual control |
| `max_conversions` | number of conversions | some conversion history, want volume, no strict CPA |
| `target_cpa` | conversions at a CPA | stable volume (≥~15–30/mo) and a known acceptable cost per sale |
| `max_conversion_value` | total conversion value | conversions carry different values, want most revenue |
| `target_roas` | value at a ROAS ratio | enough value history and a known target (e.g. 2.5) |

**Data requirement is the gate.** Smart Bidding learns from conversions; thin data (single digits/month) starves it. With ~15–30 conversions/month, start with Max conversions / Max conversion value *without* a hard target; add tCPA/tROAS once there's a stable baseline. Expect a 1–2 week learning period after every bidding change — don't stack other big changes into it.

## Experiments

For A/B testing a bidding/creative change on a live campaign, prefer a proper experiment (`experiment-create` → edit draft → `experiment-schedule`) over sequential before/after reads — Google splits traffic and reports significance (`experiment-results`).
