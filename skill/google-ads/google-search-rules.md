# Google Ads — Search Ad & Keyword Rules

## Responsive Search Ads (RSA)

Limits from Google's official Search asset specifications (verified 2026-07, API v24). The CLI's `rsa-create` enforces the hard limits client-side (preflight lint) and the API's validate-only dry-run is the final arbiter.

| Asset | Char limit | Quantity | CLI guard |
|---|---|---|---|
| Headlines | **30** | 3–15 to serve | 3–15 |
| Descriptions | **90** | 2–4 to serve | 2–4 |
| Final URL | 2,048 | 1 | required |
| Path1 / Path2 | 15 each | optional | optional |

### Copywriting rules
1. **At least one headline must contain the ad group's main keyword.** If the user searches "X", the ad must visibly say "X" — lifts relevance, CTR, Quality Score.
2. **Variety across headlines**: keyword headlines + USP/benefit + social proof + brand + CTA. Headlines of varying lengths test better.
3. **Descriptions** = the offer in detail, reasons to believe, social proof, CTA.
4. **Language = language of the keywords.**
5. **Style (editorial policy):** no exclamation marks in headlines, max one per description; no ALL-CAPS shouting (legit abbreviations like AI/SEO are fine); no emoji/symbols; no repeated punctuation. The CLI's preflight lint flags these before any API call.
6. Avoid near-duplicate headlines — the API rejects exact duplicates within one RSA.

### Official Google best practices (quantified)
- **Run ≥2 RSAs per ad group (aim 3)**, each ideally with its own final URL, all at **Good/Excellent Ad Strength**. Reported uplifts: Poor→Excellent ≈ +15 % clicks & conversions; 1→2 RSAs ≈ +6.6 % conv; 2→3 ≈ +3.7 %.
- **Ad Strength is a KPI** — the `ads` command shows it per ad.
- **Specific CTAs beat generic** ("Start the course today" over "Click here"); put prices/promos directly in assets.
- **Match the ad to the landing page** — promise X, show X.

### Pinning
Pinning forces an asset into a fixed position (syntax: trailing ` @H1`/`@H2`/`@H3`/`@D1`/`@D2` in `rsa-create`). Default = unpinned so Google optimizes the mix. **Pin the brand to Headline 1** when brand clarity matters (see Limited Ad Serving below) or when legally required. Pinning an existing ad = create a new RSA + remove the old (creative is immutable).

## Limited Ad Serving — prevention checklist

Google throttles ads of not-yet-"qualified" advertisers in higher-abuse scenarios ("unclear brand relationships or generic ads" is the common one). It is NOT a disapproval and NOT an API issue. Bake prevention into every RSA build:

1. **Pin the brand/domain to Headline position 1** on every RSA.
2. Brand must be unmistakable on the ad AND the landing page.
3. When mentioning another brand/tool, never imply affiliation — frame as independent.
4. No generic copy — be specific about who you are and what you sell.
5. Complete **Advertiser Identity Verification** (web UI only — not available via API).
6. If limited: appeal via the Limited Ad Serving Appeals Form, keep a clean record.

## Keyword match types

CLI `match_type`: `exact` | `phrase` | `broad`.

- **EXACT** `[keyword]` — that query + close variants. Tightest control. Proven high-intent terms.
- **PHRASE** `"keyword"` — queries containing the phrase meaning. Good default balance.
- **BROAD** — **AI-driven and very wide** in modern Google Ads. Powerful *with* Smart Bidding + strong negatives; budget leak without. Default new/manual/thin-data work to phrase+exact; open broad deliberately once Smart Bidding is live, and watch search terms closely.

## Negative keywords

- **Match types for negatives:** phrase (most common), exact (block one query), broad-negative (blocks any word order — use sparingly). Negatives do NOT match close variants — cover plural/typo variants explicitly.
- **Levels:** ad group (`negative-add --ad-group`) for theme exclusions; campaign (`--campaign`) for campaign junk; **shared sets** (`shared-set-*`) for lists reused across campaigns; **account-level** (`customer-negatives-attach`, max 1000) for brand-safety terms.
- Mine negatives from `search-terms` regularly — low-intent terms drain budget silently.

## Search campaign formats

- **Classic keyword search** — the CLI's core (`campaign-create` → `ad-group-create` → `keyword-add` → `rsa-create`).
- **DSA (Dynamic Search Ads)** — no keywords; Google targets + generates headlines from your pages (`dsa-setting` → `dsa-ad-group-create` → `dsa-create` → `webpage-target-add`). Great for long-tail coverage; ALWAYS pair with negatives and webpage exclusions.
- **AI Max** — newest automation layer (keywordless intent matching); managed in the UI, experiments have an `ADOPT_AI_MAX` type.
