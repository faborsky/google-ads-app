# Changelog

Verze aplikace je v `gads/__init__.py` (`__version__`, SemVer). Formát vychází z [Keep a Changelog](https://keepachangelog.com/). Datum je vydání dané verze.

## [2.2.0] — 2026-08-21 — Audit před zveřejněním: v25, opravené tiché no-op updaty, klouzavá kvóta, testy 🛡️

Kompletní kontrola appky proti aktuální dokumentaci Google Ads API (2026-08-21) a proti
štábní kultuře sesterských appek (sklik-ppc-app, meta-ads-app) před otevřením repa.

### Opraveno
- **Tiché no-op updaty kvůli field masce.** `protobuf_helpers.field_mask` porovnává hodnoty
  s výchozími, takže pole nastavené na default z masky vypadlo a API bez chyby nic neudělalo:
  **`bidding-set --strategy max_conversions` / `max_conversion_value` bez cíle a `manual_cpc`
  nikdy nepřepnuly bidding**, **`device-bid --modifier 0` (vypnout zařízení) nic nevypnul** u
  existujícího kritéria a **`conversion-update --primary no` nechal akci primary**. Nová
  presence-aware maska (`api._field_mask`, rekurzivně z `ListFields()`; prázdné bidding zprávy
  jmenují subfield dle dokumentovaného workaroundu na `FIELD_HAS_SUBFIELDS`) + regresní testy.
  Nalezeno offline testy proti proto typům, opravené cesty ověřeny živě přes validate_only.
- **`pmax-search-terms` měl natvrdo `LIMIT 500`** — stejná třída chyby jako tiché usekávání
  výpisů ve Sklik appce (1.9.0). Odstraněno; volitelný `--limit` výstup jen zkrátí a řekne to.
  Audit všech ostatních výpisů: žádný jiný hardcoded LIMIT (search_stream vrací vše).
- **`changes` upozorní na useknutí** — API tu LIMIT vyžaduje; když přijde přesně LIMIT řádků,
  CLI varuje (zvyš `--limit` / zkrať `--days`). `keywords-research --limit` říká „prvních N z M".
- **`--json` za názvem příkazu** (`./run.sh pulse <cid> --json`) končilo `unrecognized arguments`
  — README i skill ho tak přitom psaly. Teď funguje před i za příkazem.
- **Čisté chyby místo tracebacků**: expirovaný/odvolaný refresh token (`invalid_grant` → „consent
  screen v Testing vyprší po 7 dnech, spusť `auth`"), špatný OAuth klient, neschválený developer
  token / Cloud projekt (`DEVELOPER_TOKEN_NOT_APPROVED`, `CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION`,
  `USER_PERMISSION_DENIED`… s radou), síťové výpadky (`UNAVAILABLE` — u čtení retry, u zápisu
  jasně „neopakuji, zápis mohl projít"), Ctrl-C.
- `accounts` vypisuje **celou hierarchii MCC** (dřív jen první úroveň — účty pod sub-managery
  chyběly); zavřené účty skryté.

### Změněno
- **API pin v24 → v25** (knihovna `google-ads` 31.4.0, podporuje v25.1). Breaking changes v25
  se appky netýkají (ověřeno proti release notes); každá operace CLI je navíc ověřená offline
  testy proti proto stubům v25. Python 3.10–3.14 (knihovna zatím nejede na 3.15).
- **Kvóta se počítá klouzavě za 24 h** (tak ji měří Google — „sliding 24 hour period" v docs),
  ne po pacifických dnech. `.quota/<account>.json` je log operací, `quota` ukazuje, za jak
  dlouho nejstarší operace vypadne z okna. **validate_only dry-runy se počítají taky** —
  Google výjimku nikde nedokumentuje, dřívější „dry-runy zdarma" bylo nepodložené; lokální
  odhad je tak vždy ≥ realita.
- **`./run.sh auth` zapisuje refresh token rovnou do `.env`** (atomicky, chmod 600, záloha
  `.env.bak`) — token už neprochází terminálem ani chatem agenta. `--print` ho místo toho vypíše.
  `setup.sh` nastavuje `.env` na 600.
- `api-limits` nese verzi API, úrovně přístupu (Test/Explorer/Basic/Standard) a klouzavé okno.

### Přidáno
- **Service account** jako alternativní autentizace (`GOOGLE_ADS_JSON_KEY_FILE_PATH`, volitelně
  `GOOGLE_ADS_IMPERSONATED_EMAIL`) — bez prohlížeče, bez 7denní expirace; pro crony a agenty.
- **Offline testovací sada `tests/` (107 testů, pytest)** — reálný `GoogleAdsClient` na v25
  stubech + recorder místo gRPC: každý zápisový příkaz staví operace proti skutečným typům API
  (překlep v poli/enumu = červený test), dry-run default, pojistka PAUSED-před-REMOVED, klouzavá
  kvóta, retry politika, masky, lint, zápis tokenu do `.env`, CLI bez přístupů. `requirements-dev.txt`.
- **MIT LICENSE** + sekce Licence, Chyby a náměty, Testy, Struktura projektu, O kurzu a Windows v README.

### Dokumentace
- README → **Autentizace přepsaná podle aktuálních docs**: přístupové úrovně tokenu (nově dostáváš
  typicky **Explorer Access** — produkce OK, 2 880 ops/den, **Keyword Planner zablokovaný** →
  `keywords-research` až s Basic Access; review ~5 dní; brand verification Cloud projektu
  volitelně zrychlí), OAuth consent screen **In production** (jinak 7denní expirace tokenu),
  service account krok za krokem, testovací účty, jeden Cloud projekt = jeden developer token.
- `docs/api-notes.md`: v25/v25.1, access levels, klouzavá kvóta, validate_only, service accounts,
  field-mask past, CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION. CLAUDE.md: pravidla „presence-aware
  maska" a „nikdy hardcoded LIMIT", release checklist s pytestem a GitHub Release. Skill: kvóta,
  Keyword Planner vyžaduje Basic Access.

## [2.1.0] — 2026-07-19 — Vizuální podpis 🎨

- **ASCII banner s barvami** („GADS" v Google barvách — modrá/červená/žlutá/zelená + verze, tagline a „by Jindřich Fáborský · AIFirst.cz") — vypíše se **jen člověku v terminálu** (stdout je TTY a neběží `--json`). Pipe, skripty a agentní tool-cally dostávají dál čistý výstup bez jediného znaku navíc. Respektuje `NO_COLOR`.

## [2.0.0] — 2026-07-19 — Velký refresh: 19 → 85 příkazů, balík, policy kontroly 🚀

Kompletní přestavba podle gap analýzy aktuální dokumentace Google Ads API (v24, ověřeno 2026-07-19). Monolit `google_ads_cli.py` (1181 ř.) je nově balík `gads/` (engine `api.py`, `formatting`, `lint`, `commands/*` po doménách, `cli.py`); entrypoint zůstává, všech 19 původních příkazů funguje beze změny. Knihovna `google-ads` 31.1.0.

- **`pulse`** — přehled účtu v 5 operacích: totály, per-kampaň metriky, delty vs. předchozí stejně dlouhé okno, top movery, optimization score, počet doporučení Googlu, počet inzerátů s policy problémem. Navíc automatické varovné signály: primary konverze 0 při nenulových all_conversions (rozbité měření) a kampaně limitované rozpočtem (lost IS >10 %). Okno končí včerejškem (dnešní data jsou neúplná).
- **Mechanismus kontroly pravidel inzerce** (trojitá pojistka): (1) **preflight lint** — lokální kontrola RSA/asset textů PŘED voláním API: počty a délky natvrdo, stylové nálezy (vykřičník v headline, CAPS, opakovaná interpunkce, emoji, duplicity) jako varování; (2) `validate_only` dry-run zůstává default každé mutace; (3) **`ad-policy`** — approval status (APPROVED/LIMITED/DISAPPROVED) + policy topics po asynchronním schválení (`--only-problems`).
- **Záchranná brzda „PAUSED před REMOVED"**: Google Ads nemá undelete — REMOVED je trvalé. `campaign-status`/`ad-status --status removed` nově odmítne entitu, která není pauznutá (vědomé obejití `--force`).
- **Assets: sitelinky, callouts, structured snippets** — tvorba (`sitelink-create`/`callout-create`/`snippet-create` s lint kontrolou limitů), výpis (`assets`, `asset-links`) a napojování na účet/kampaň/sestavu (`asset-link`/`asset-unlink`). Assety jsou v API create-only — „editace" = nový asset + přepojení.
- **Publika/remarketing**: `audiences` (vč. size_for_search a eligibility), `audience-create` (rule-based návštěvníci URL), `audience-attach` s režimem **Observation vs. Targeting** (přepíná targeting_setting entity), `audience-exclude` (vyloučení publika z kampaně), `audiences-attached`, `audience-detach`.
- **Cílení kampaní**: `geo-suggest` (hledání geo ID podle názvu), `geo-target` (+ vyloučení + proximity radius), `language-target`, `schedule-set` (atomická náhrada rozvrhu), `device-bid` (0 = vypnout zařízení), `demographics`/`demographic-target` (věk/pohlaví/příjem vč. vyloučení). **`campaign-create` nově nastavuje geo + jazyk** (výchozí ČR + čeština) — kampaň bez těchto kritérií běží na celý svět; `campaign-targeting` to zkontroluje.
- **Shared sets negativ**: `shared-set-create/add/keywords/remove-keywords/attach/remove` + **account-level negativa** (`customer-negatives-attach`/`customer-negatives-detach`, typ ACCOUNT_LEVEL_NEGATIVE_KEYWORDS, max 1000/účet).
- **Konverzní akce**: `conversions` (primary/secondary, counting), `conversion-create` (WEBPAGE), `conversion-update` (status, primary_for_goal, counting, default value).
- **Recommendations**: `recommendations` (typ, dopad, doporučený rozpočet/keyword), `recommendation-apply`, `recommendation-dismiss`. Pozor: resource names doporučení rychle stárnou (regenerují se denně).
- **Change history**: `changes` — kdo co změnil (change_event, ≤30 dní, staré→nové hodnoty, e-mail autora) a `--sweep` (change_status, ≤90 dní, levný přehled co se hnulo).
- **Rozpočty**: `budgets` (vč. Googlem doporučených částek), `budget-create` (sdílený rozpočet), `budget-assign`, `budget-remove` (úklid sirotků); `budget-set` varuje u sdíleného rozpočtu.
- **DSA**: `dsa-setting` (doména+jazyk na kampani), `dsa-ad-group-create` (SEARCH_DYNAMIC_ADS), `dsa-create` (descriptions-only inzerát), `webpage-targets`/`webpage-target-add`/`webpage-target-remove` (cílení na stránky vč. vyloučení).
- **PMax reporting-only**: `pmax` (metriky, `--channels` = rozpad po sítích), `pmax-search-terms` (campaign_search_term_view — běžný search_term_view PMax nevidí).
- **Experiments**: `experiment-create` (SEARCH_CUSTOM + obě arms jedním requestem, vrací draft kampaň), `experiment-schedule/end/promote`, `experiments`, `experiment-results` (treatment vs. control).
- **Výpisy, které chyběly**: `ad-groups`, `ads` (status + Ad Strength + approval), `keywords` (s criterion ID pro remove), `labels` + `label-create/assign/unassign/remove`.
- **Oprava latentního bugu z v1**: kampaň nejde smazat status updatem (`Enum value 'REMOVED' cannot be used`) — `campaign-status --status removed` nově správně používá remove operaci (ověřeno živě).
- **Vše otestováno živě** na sandbox PAUSED kampani (vytvořena → proklikáno všech ~40 write příkazů → uklizeno); živé nálezy zapsané v `docs/api-notes.md`.
- **`api-limits`** — dokumentované limity API (Basic 15k ops/den, mutate ≤10k ops/request, Keyword Planner 1 QPS, okna change history) + živé lokální čerpání kvóty.
- **Výpisy defaultně filtrují REMOVED entity** (REMOVED zůstávají v API viditelné navždy); `--status removed` je zobrazí.
- **Tooling**: `scripts/check_docs_consistency.py` — mechanická kontrola CLI ↔ README ↔ CLAUDE.md ↔ skill (příkazy, počty, verze, fantomy). `--version` flag.
- **Bundled skill `skill/google-ads/`** + `skill/INSTALL.md` — kanonická operátorská skill pro Claude Code (scénáře research/create/optimize/policy-check/negatives/audiences, bezpečnostní pravidla), instalace s `<GADS_APP_DIR>` placeholderem.

## [1.1.0] — 2026-07-14 — Tvrdý quota guard, QPS retry, RSA pinning 🛡️

- **Hard stop před překročením denní kvóty**: `_quota_guard` běží PŘED každým reálným voláním (read = 1 op, write = počet operací při `--confirm`) a skončí chybou, když by volání překročilo denní cap (`GOOGLE_ADS_DAILY_OP_CAP`, default 15 000 = Basic Access) — runaway smyčka nemůže vyčerpat účet. Oprava počítání: Search/SearchStream request = **1 operace bez ohledu na počet řádků** (dříve konzervativně počítáno po řádcích).
- **QPS retry s exponenciálním back-offem**: `RESOURCE_EXHAUSTED`/`RESOURCE_TEMPORARILY_EXHAUSTED` se retryuje 5→10→20 s (respektuje Googlem doporučený `retry_delay`), max 3 pokusy, pak abort. Ostatní chyby dál končí srozumitelným výpisem.
- **RSA pinning**: inline syntaxe ` @H1`/`@H2`/`@H3`/`@D1`/`@D2` v `rsa-create` — připnutí brandu na Headline 1 (prevence Limited Ad Serving).
- Počítadlo kvóty bucketuje podle **pacifického data** (reset kvóty Googlu je půlnoc America/Los_Angeles).

## [1.0.0] — 2026-06-09 — První verze: read + write základ

Single-file CLI (`google_ads_cli.py`) nad oficiální `google-ads` knihovnou (API v24), OAuth2 přes `.env`, multi-account přes env suffixy. 19 příkazů:

- **Čtení**: `accounts` (MCC hierarchie), `query` (GAQL), `report` (presety campaign/ad_group/keyword), `campaigns`, `search-terms`, `keywords-research` (Keyword Planner), `quota`.
- **Zápisy** — všechny defaultně `validate_only` dry-run + plán, reálný zápis až s `--confirm`: `campaign-create` (SEARCH, startuje PAUSED, budget atomicky), `campaign-status`, `ad-group-create`, `rsa-create` (limity 3–15/2–4 hlídané klientsky), `keyword-add` (JSON batch), `keyword-remove`, `negative-add` (sestava/kampaň), `budget-set`, `bidding-set` (manual CPC, Max conversions/value, tCPA, tROAS), `ad-status`, `ad-update-url` (Final URL je jediné in-place editovatelné pole inzerátu).
- Lokální tracking denní kvóty per účet/den v `.quota/`.
