# Google Ads API — behaviour notes & gotchas

Jediná reference toho, jak se Google Ads API reálně chová (ověřeno proti oficiální dokumentaci na developers.google.com/google-ads/api, **2026-08-21**, verze **v25**; položky označené „živě" jsou navíc ověřené během vývoje na reálném účtu). CLAUDE.md odkazuje sem; hluboký detail patří sem, signpost zůstává štíhlý.

## Verze & knihovna

- **API pinned na v25** (`API_VERSION` v `gads/api.py`). v25 vyšla 2026-07-22 (sunset srpen 2027), minor v25.1 2026-08-19 (bez breaking changes). v24 (předchozí pin) má sunset květen 2027. Google drží ~5 verzí naráz, major žije ~12 měsíců; upgrade nemusí být sekvenční. Sunset tabulka: developers.google.com/google-ads/api/docs/sunset-dates.
- Breaking changes v25 se téhle appky netýkají (lifecycle goals → Goal/CampaignGoalConfig, Incentive service, LocalServicesLead, reach planning, benchmarks). Ověřeno proti release notes při bumpu pinu. Nová věc v v25.1: `AuthorizationError.CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION` — Cloud projekt s TEST úrovní proti produkčnímu účtu (CLI hlášku překládá na radu).
- Python knihovna `google-ads` **31.4.0** (v25 podporuje od 31.2.0; 31.4.0 = v25.1; Python ≥3.9, <3.15). Verze knihovny ≠ verze API. Další plánované verze: v25.2 (září 2026), v26 (říjen 2026).

## Přístupové úrovně developer tokenu

Každý token má **access level** (+ „permissible use"). Po registraci v API Center dostaneš typicky **Explorer Access** (automaticky), jinak Test Account Access:

| Úroveň | Účty | Denní limit | Omezení |
|---|---|---|---|
| Test Account Access | jen testovací | 15 000 | produkce → `DEVELOPER_TOKEN_NOT_APPROVED` |
| Explorer Access | testovací + produkční | **2 880** na produkci (15 000 na test) | **blokované služby**: Keyword Planner (`KeywordPlanIdeaService` & spol.), AudienceInsights, ReachPlan, billing, account creation, user management |
| Basic Access | testovací + produkční | 15 000 | review ~5 pracovních dní; brand verification Cloud projektu volitelně zrychlí |
| Standard Access | testovací + produkční | bez limitu | review ~10 dní; jen pro velké nástroje |

Jeden Cloud projekt smí používat jen jeden developer token (jinak `DEVELOPER_TOKEN_PROHIBITED`). Jednotlivec může o token žádat jako „Individual" s URL profilu (GitHub/LinkedIn); generické URL Google odmítá.

## Kvóty & rate limity

- **Denní kvóta je na developer token a měří se klouzavě za posledních 24 h** („per day is based on a sliding 24 hour time period" — access-levels docs), ne po kalendářním dnu/půlnoci Pacific. Operace = get požadavky + mutate operace. Překročení → `RESOURCE_EXHAUSTED`.
- **Search/SearchStream request = 1 operace bez ohledu na počet řádků/batchů** (doslova v docs). Stránkování přes platný `next_page_token` se nepočítá. Mutace = 1 op za každou operation v requestu; max **10 000 operací v jednom mutate requestu** (`TOO_MANY_MUTATE_OPERATIONS`). Požadavky odmítnuté s `GoogleAdsFailure` se počítají; síťové chyby ne.
- **`validate_only`**: Google **nedokumentuje**, že by byly dry-runy z kvóty vyjmuté → CLI je počítá taky (lokální odhad je vždy ≥ realita). Dříve jsme psali „zdarma" — nepodložené.
- CLI trackuje operace lokálně per účet v `.quota/<account>.json` (log `[timestamp, ops]`, ořezávaný na 24 h) a **hard-stopuje před** voláním, které by cap překročilo (`GOOGLE_ADS_DAILY_OP_CAP`). Je to lokální odhad, ne serverové číslo — autoritativní je Cloud Console → APIs & Services → Google Ads API (metriky per metoda).
- gRPC odpověď max **64 MB** — u širokých SELECTů vyber míň polí (CLI streamuje vždy).
- **QPS limity** jsou oddělené od denní kvóty, metrované **per client CID + developer token**, token-bucket, přesné číslo Google nepublikuje (mění se podle zátěže). Porušení → `RESOURCE_TEMPORARILY_EXHAUSTED` (rate) / `RESOURCE_EXHAUSTED`; chyba nese `QuotaErrorDetails.retry_delay` (doporučená pauza). CLI retryuje 5→10→20 s (oficiálně doporučené schéma), respektuje `retry_delay`, max 3 pokusy, pak abort — nikdy nemlátí do API ve smyčce. Doporučení Googlu: omezit paralelní tasky, batchovat mutace, throttlovat na klientu.
- **Planning services (Keyword Planner / GenerateKeywordIdeas / HistoricalMetrics / ForecastMetrics) = 1 request/s per CID** (60 za 60 s) — víc keyword-research požadavků pouštěj sekvenčně. A vyžadují Basic Access.

## Autentizace

- **Installed-app OAuth2** (refresh token): Cloud projekt s povoleným Google Ads API + OAuth consent screen (External) + klient typu Desktop app. **Consent screen v režimu „Testing" = refresh token expiruje po 7 dnech** (Google Identity docs) → `invalid_grant` při refreshi. Řešení: publishing status „In production" (neověřená appka ukáže varování, ale funguje; ověření pro vlastní nástroj není nutné). Další důvody zneplatnění: odvolání přístupu, 6 měsíců nepoužití, >100 živých refresh tokenů na klienta, změna hesla (jen Gmail scopes).
- **Service account**: Google Ads API ho ověří **přímo** — e-mail service accountu se přidá jako uživatel účtu/MCC (Admin → Access and security), Workspace ani domain-wide delegation netřeba (`impersonated_email` je volitelný). Python config klíč `json_key_file_path` (knihovna vybírá flow podle PŘÍTOMNOSTI klíčů v configu, proto CLI v SA režimu vynechá client_id/secret/refresh_token). Admin roli SA default nedostane (jde upgradovat v UI).
- `login_customer_id` = MCC bez pomlček; cílový účet = `customer_id` requestu. Uživatel bez přístupu → `USER_PERMISSION_DENIED`.

## Živě ověřené quirky (sandbox roundtrip 2026-07-19, účet s PAUSED testovací kampaní)

- **Kampaň nejde „updatovat na REMOVED"** — API vrátí `Enum value 'REMOVED' cannot be used`. Odstranění kampaně (stejně jako inzerátu) vyžaduje **remove operation**. CLI to řeší v `campaign-status`/`ad-status`.
- **Nová kampaň dostane od Googlu implicitní DEVICE kritéria** (criterion ID 30000=DESKTOP, 30001=MOBILE, 30002=TABLET) — `device-bid` proto existující kritérium updatuje místo create.
- **`recommendation.impact.*` a další vnořená pole recommendation NEJSOU selectable v GAQL** — vybírat jde jen celé submessages (`recommendation.impact`, `recommendation.campaign_budget_recommendation`…).
- **`change_event.changed_fields` (FieldMask) se v `MessageToDict` mapuje na STRING** `"a,b,c"`, ne na objekt s `paths`.
- **`ConversionActionCategoryEnum` nemá generickou hodnotu `LEAD`** — jen konkrétní podtypy (SUBMIT_LEAD_FORM, PHONE_CALL_LEAD, QUALIFIED_LEAD, CONVERTED_LEAD…); navíc existuje YOUTUBE_FOLLOW_ON_VIEWS.
- **Experiment jde založit i na PAUSED kampani** (vč. vygenerování draft kampaně). **Experiment v SETUP nejde „ukončit"** — ruší se remove operací (`experiment-end` v CLI to rozliší podle statusu sám).
- **Testovací assety zůstávají v knihovně navždy** (create-only) — počítej s tím při experimentování; nenapojené assety ale nikde neslouží.
- `audience-attach --mode observation` úspěšně přepíná `targeting_setting.target_restrictions` entity (přeposílá se celý seznam restrictions).
- Ne-živě ověřené cesty (chování dle oficiálních docs): `recommendation-apply/dismiss` s reálným doporučením (účet žádné neměl), `experiment-schedule/promote` (spustily by utrácení), `conversion-create/update --confirm` (testováno validate-only, ať v účtu nezůstávají testovací akce).
- Bump na v25 (2026-08-21) ověřen **offline** proti proto stubům v25 (každá operace CLI se staví z reálných typů v testech) + release notes; živý roundtrip na v25 je na seznamu pro první použití.

## Mutace obecně

- Všechny mutate requesty berou `validate_only` (kromě `ApplyRecommendationRequest`, `DismissRecommendationRequest` a experiment lifecycle metod — tam CLI dry-run řeší „jen plán, nic nevolám").
- Nové entity jdou vytvářet **atomicky v jednom `GoogleAdsService.Mutate`** s temp resource names (`customers/{cid}/campaignBudgets/-1`, kampaň `-2`…) — tak dělá `campaign-create` budget + kampaň + geo/language kritéria najednou (all-or-nothing).
- **Update = resource_name + změněná pole + field mask.** Pole mimo masku se nemění. **POZOR na masku u výchozích hodnot**: `protobuf_helpers.field_mask(None, msg)` porovnává HODNOTY s defaulty, takže pole záměrně nastavené na default (`primary_for_goal = False`, `bid_modifier = 0`, prázdná bidding zpráva `manual_cpc`/`maximize_conversions`) z masky vypadne a API provede **tichý no-op** (žádná chyba). Zároveň maska **nesmí jmenovat prázdné message pole** (`FieldMaskError.FIELD_HAS_SUBFIELDS`, ověřeno živě na v25) — dokumentovaný workaround Googlu je pojmenovat jeden mutable subfield, např. `maximize_conversions.target_cpa_micros` (nikdy `cpc_bid_ceiling/floor` — ty jsou portfolio-only). CLI proto staví masku presence-aware rekurzí přes `ListFields()` s leaf mapou pro prázdné bidding zprávy (`api._field_mask`); do 2.2.0 tak `bidding-set max_conversions`/`manual_cpc`, `device-bid --modifier 0` a `conversion-update --primary no` nic neudělaly. Všechny čtyři cesty ověřeny živě přes validate_only (2026-08-21).
- **REMOVED je trvalé — žádné undelete.** REMOVED entity navíc **zůstávají ve výpisech navždy** (výchozí GAQL filtry CLI je skrývají: `status != 'REMOVED'`). Záchranná brzda CLI: remove jde jen na PAUSED entitu (`--force` obejde).
- **Status update na REMOVED tiše ne-funguje** u ad_group_ad — remove vyžaduje remove operation, ne update statusu. CLI to řeší správně; nikdy „neopravovat zpět".
- Přechodné transportní chyby (`UNAVAILABLE`, `DEADLINE_EXCEEDED`, `INTERNAL`) u zápisu CLI **neopakuje** — zápis mohl projít; u čtení ano.

## Inzeráty (RSA)

- **Kreativa je immutabilní.** Jediná in-place editovatelná pole jsou URL (`AdService.mutate_ads` → `ad-update-url`, drží historii výkonu). Změna textu = nová RSA + odstranit starou (pauza → remove). Není to porušení ToS, jen technická vlastnost — `AdGroupAdService` u update honoruje jen `status` a ostatní pole **tiše ignoruje** (žádná chyba!).
- RSA limity: 3–15 headlines ≤30 znaků, 2–4 descriptions ≤90, path1/2 ≤15. Duplicity textů v jedné RSA API odmítne. Pinning přes `AdTextAsset.pinned_field` (`ServedAssetFieldTypeEnum`).
- **`policy_summary`** na ad_group_ad (output-only): `approval_status` (APPROVED / APPROVED_LIMITED / AREA_OF_INTEREST_ONLY / DISAPPROVED), `review_status` (REVIEW_IN_PROGRESS / REVIEWED / UNDER_APPEAL / ELIGIBLE_MAY_SERVE), `policy_topic_entries[]` (topic + typ). Schvalování je asynchronní (typicky ≤1 pracovní den) — po `rsa-create` zkontroluj `ad-policy`.
- Exemption mechanismus existuje (`policy_validation_parameter` v mutate: ads → `ignorable_policy_topics`, keywords → `exempt_policy_violation_keys`) — CLI ho zatím newrapuje; chybu s policy violation vypíše.
- v25.1 přidala `AssetFieldType.TEXT_DISCLAIMER` (text disclaimer assety) — CLI zatím newrapuje.

## Assets (sitelinky, callouts, structured snippets)

- **AssetService umí jen CREATE** — asset nejde upravit ani smazat; spravují se jen **linky** (CustomerAsset / CampaignAsset / AdGroupAsset, remove přes composite resource name `{parent}~{assetId}~{FIELD_TYPE}`). „Editace" = nový asset + přepojit link.
- Feed-based extensions (FeedService & spol.) byly **odstraněny v v19** — assets jsou jediná cesta.
- Limity: sitelink link_text 1–25, description1/2 1–35 (oba nebo žádný); callout 1–25; structured snippet header z **pevného anglického seznamu 13 hodnot** (Google lokalizuje sám), values 3–10 × 1–25. Search potřebuje **≥2 sitelinky**, aby se zobrazovaly.
- Nižší úroveň přebíjí vyšší (sitelinky sestavy potlačí kampaňové/účtové).
- Duplicitní obsah assetu API tiše sloučí s existujícím (vrátí existující ID).

## Publika

- Rule-based listy: `FlexibleRuleUserListInfo` (operandy s `UserListRuleInfo` → rule_item_groups → rule_items; `url__` + CONTAINS je základní vzor). `prepopulation_status = REQUESTED` = zpětné naplnění ~30 dní. Lookalike listy jsou read-only (vytváří systém); Customer Match = separátní OfflineUserDataJob flow (CLI newrapuje; od 2026-04-01 navíc pro developer tokeny bez historie Customer Match selhává → Data Manager API).
- Napojení = campaign_criterion / ad_group_criterion s `user_list`. **Pozitivní kritéria nemůžou být na kampani i sestavě téže kampaně zároveň.** Pozitivní kampaňová publika fungují jen na SEARCH. Vyloučení (`negative=true`) funguje na kampani.
- **Observation vs. Targeting nesedí na kritériu, ale na entitě**: `targeting_setting.target_restrictions[]` kampaně/sestavy, dimenze AUDIENCE, `bid_only=true` = Observation. Update = přeposlat celý seznam restrictions. Quirk: nejde nastavit na sestavě, když je nastaveno na kampani (a naopak).
- Serving minimum na search ≈ 100 aktivních uživatelů/30 dní; sbírání vyžaduje web tag.

## Cílení

- Geo: `GeoTargetConstantService.SuggestGeoTargetConstants` (name lookup s reach); kritérium `location.geo_target_constant`; vyloučení `negative=true`. ČR = `2203`. `geo_target_type_setting` kampaně: default PRESENCE_OR_INTEREST.
- Proximity: `proximity.geo_point` (souřadnice v **mikro-stupních**, int) + radius + units; **nejde negovat**.
- Jazyk: `language.language_constant`, **jen pozitivní** (bez vyloučení). Čeština = `1021`, slovenština `1034`, angličtina `1000`.
- Ad schedule: campaign criterion, celé hodiny (minuty jen po čtvrthodinách), **max 6 bloků/den**, s bid_modifierem. Změna = remove + create (kritéria jsou immutabilní kromě bid_modifier) — `schedule-set` dělá atomickou náhradu v jednom requestu.
- Device: campaign criterion `device.type` + `bid_modifier` 0.1–10.0; **`bid_modifier = 0` = zařízení vypnout** (ekvivalent −100 % v UI; negativní device kritéria neexistují). Existující kritérium se updatuje (bid_modifier je výjimka z immutability) — a 0 musí být v masce explicitně (viz Mutace).
- Demografie (věk/pohlaví/příjem): ad_group_criterion, positive i negative.

## Negativa & shared sets

- Úrovně: sestava (ad_group_criterion), kampaň (campaign_criterion), **shared set** (SharedSet typu NEGATIVE_KEYWORDS → SharedCriterion → CampaignSharedSet), **účet** (SharedSet typu ACCOUNT_LEVEL_NEGATIVE_KEYWORDS připojený přes `CustomerNegativeCriterion.negative_keyword_list` — přímé keyword pole na CustomerNegativeCriterion NEEXISTUJE).
- Limity: 20 listů/účet, 5 000 negativ/list, account-level max 1 000/účet. **Negativa nematchují close variants** — varianty pokrývej explicitně.

## Konverze

- `conversion_action`: `type` je immutable (WEBPAGE, UPLOAD_CLICKS…); `primary_for_goal` řídí, jestli akce sytí `metrics.conversions` (= co optimalizuje bidding); `all_conversions` počítá všechno. Writable atribuční modely už jen GOOGLE_ADS_LAST_CLICK a data-driven.
- Offline import: od 2026-06-15 `UploadClickConversions` **selhává pro developer tokeny, které nikdy předtím neimportovaly** — nové integrace musí přes Data Manager API. Proto CLI offline import newrapuje.

## Recommendations & optimization score

- GAQL `recommendation` (typ + impact + per-typ detail union). `customer.optimization_score` a `campaign.optimization_score` (0–1). Apply = `RecommendationService.ApplyRecommendation` (per-typ `apply_parameters` na override — CLI aplikuje bez overridů), dismiss = `DismissRecommendation`. Oba **bez `validate_only`** (dry-run CLI = jen plán) a počítají se do kvóty.
- **Resource names doporučení stárnou** (regenerace denně i častěji) — list a apply/dismiss v jedné session.

## Change history

- `change_event`: plné staré→nové snapshoty + `changed_fields` + `user_email` + `client_type`; **povinný WHERE na change_date_time ≤ posledních 30 dní a povinný LIMIT ≤ 10 000**; ~3 min zpoždění; nepokrývá úplně všechny typy entit.
- `change_status`: levný „co se hnulo" (bez hodnot polí), okno ≤ 90 dní, stejný povinný LIMIT; vrací jen poslední změnu entity v okně.
- Protože LIMIT je povinný, CLI hlídá useknutí: vrátí-li API přesně LIMIT řádků, vypíše varování (zvyš `--limit` / zkrať `--days`).

## Rozpočty

- `explicitly_shared` **defaultuje na TRUE v API create** (opak UI) — CLI ho vždy nastavuje explicitně. Konverze non-shared → shared jde (jedním op se jménem); **shared → non-shared nejde nikdy**. `reference_count` = počet připojených kampaní.
- Doporučení rozpočtu přímo na `campaign_budget`: `has_recommended_budget`, `recommended_budget_amount_micros` (+ odhady dopadu). Google může utratit až ~2× denní rozpočet v silný den (měsíční cap 30,4×).

## DSA

- Kampaň: normální SEARCH + `dynamic_search_ads_setting` (domain_name, language_code). Sestava: `type = SEARCH_DYNAMIC_ADS` (immutable) — **žádné pozitivní keywords, žádné RSA** uvnitř. Inzerát: `expanded_dynamic_search_ad` jen s description(1–2) — headline/URL generuje Google.
- Cílení: webpage criteria, 1–3 AND podmínky (URL/PAGE_TITLE/PAGE_CONTENT partial; CATEGORY exact; CUSTOM_LABEL pro page feedy); negativní webpage kritéria fungují. Page feedy (AssetSet typu PAGE_FEED) CLI zatím newrapuje.

## PMax

- Plná správa přes API existuje (AssetGroupService…), ale CLI je záměrně **reporting-only**: PMax nemá ad_group/ad_group_ad řádky; search terms jen přes `campaign_search_term_view` (běžný `search_term_view` PMax vynechává, stejně tak dotazy s `keyword.*` segmenty); od v23 funguje `segments.ad_network_type` i na cost (rozpad utrácení po sítích). Search terms CLI čte bez LIMITu (do 2.2.0 bylo natvrdo `LIMIT 500` = tiché useknutí).

## Experiments

- `ExperimentService` + `ExperimentArmService` (starý CampaignExperimentService už není). Flow: experiment (SEARCH_CUSTOM, SETUP) → **obě arms v JEDNOM requestu** (control s kampaní + treatment; traffic_split součet 100) → treatment vygeneruje draft kampaň (`in_design_campaigns`; v GAQL viditelná jen s `include_drafts=true`) → upravit draft → `ScheduleExperiment` (async long-running op). Konec: `End` (nic se neaplikuje) / `Promote` (async, přepíše base kampaň) / `Graduate`.
- Limity: ≤5 naplánovaných experimentů na kampaň, 1 běžící; start plánuj do budoucna (review inzerátů). Reporting: `experiment` resource s párovými metrikami (`metrics.clicks` vs `metrics.control_clicks`, + p-values). v24.2 přidala typy COMPARE_CAMPAIGNS a PMAX_TEXT_CUSTOMIZATION_FINAL_URL_EXPANSION (CLI dělá jen SEARCH_CUSTOM).

## GAQL specifika

- Date literals: `TODAY`, `YESTERDAY`, `LAST_7_DAYS`, `LAST_30_DAYS`, `THIS_MONTH`… — **`LAST_90_DAYS` neexistuje**, použij `BETWEEN`.
- Enum hodnoty ve WHERE se píší jako stringy (`campaign.status = 'PAUSED'`), resource names s prefixem (`customers/{cid}/...`).
- `search_stream` vrací streamované batches a **celý výsledek** (žádné stránkování/useknutí); CLI je skládá do jednoho seznamu a listingy proto žádný `LIMIT` nemají. `--json` výstup = `MessageToDict` (camelCase klíče!).
- Composite resource names: `adGroupAds/{agId}~{adId}`, `adGroupCriteria/{agId}~{critId}`, `campaignCriteria/{cId}~{critId}`, `campaignAssets/{cId}~{assetId}~{FIELD_TYPE}`, `campaignSharedSets/{cId}~{setId}`, `adGroupCriterionLabels/{agId}~{critId}~{labelId}`.

## Chyby

- `GoogleAdsException.failure.errors[]` nese message + `location.field_path_elements` (které pole) + typované error kódy; CLI je vypisuje čitelně s `request_id` a u autorizačních kódů (`DEVELOPER_TOKEN_NOT_APPROVED`, `CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION`, `DEVELOPER_TOKEN_PROHIBITED`, `USER_PERMISSION_DENIED`, `CUSTOMER_NOT_ENABLED`) přidá radu.
- Rate chyby (`quota_error`) mají `quota_error_details.retry_delay` — CLI ho honoruje.
- OAuth chyby (`RefreshError: invalid_grant` = expirovaný/odvolaný refresh token; `invalid_client` = špatný OAuth klient) CLI překládá na čitelnou radu místo tracebacku.
- EU political advertising: nové kampaně vyžadují `contains_eu_political_advertising` (CLI posílá DOES_NOT_CONTAIN…).
