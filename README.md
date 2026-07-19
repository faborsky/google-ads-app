# Google Ads App

CLI aplikace pro správu **search kampaní na Google Ads** přes oficiální [Google Ads API](https://developers.google.com/google-ads/api) (v24, knihovna `google-ads` 31.x).

Pokrývá kompletní životní cyklus search kampaní — kampaně, sestavy, RSA inzeráty, klíčová slova, negativa (vč. sdílených seznamů), assety (sitelinky/callouts/snippety), publika a remarketing, cílení (geo/jazyk/rozvrh/zařízení/demografie), rozpočty, Smart Bidding, konverzní akce, doporučení Googlu, kontrolu schválení inzerátů, change history, experimenty a GAQL reporting. Display/YouTube/Shopping neřeší; Performance Max jen reportuje.

> 🎓 **Tahle appka je doprovodný materiál ke kurzu [AI First](https://aifirst.cz).** Ukazuju na ní marketérům, jak si vibe codingem postavit vlastní nástroj, který za vás dělá rutinu (tady správu Google Ads z Claude Code) a šetří hodiny času. Součástí repa je i [skill pro Claude Code](#skill-pro-claude-code-google-ads), který appku obaluje. Chceš se to naučit prakticky? → **[aifirst.cz](https://aifirst.cz)**

## 🆕 Co je nového

Aktuální verze **2.1.0** — vizuální podpis (ASCII banner jen pro lidi v terminálu). Předtím 2.0.0 — velký refresh: 19 → **85 příkazů** (pulse, assety, publika, cílení, shared sets, konverze, recommendations, change history, DSA, experimenty), balík `gads/`, preflight lint textů, policy kontroly, pojistka „PAUSED před REMOVED". Celá historie: **[CHANGELOG.md](CHANGELOG.md)**. Novinky odebírej přes GitHub: **Watch → Custom → Releases**.

## Dva způsoby, jak appku používat

**A) Orchestrace přes Claude Code (výchozí a nejjednodušší).** Appku řídí Claude Code (nebo jiný coding agent) přes přibalený skill — zadáváš cíle česky, agent volá CLI, drží bezpečnostní pravidla (plán → schválení → zápis, dry-run default, kvóty, „REMOVED je trvalé") a zná quirky API. Nejrychlejší start: otevři Claude Code a vlož mu prompt typu:

> *Naklonuj https://github.com/faborsky/google-ads-app, spusť `./setup.sh`, nainstaluj mi přibalený skill podle `skill/INSTALL.md` a pak mě provoď získáním přístupů do `.env` podle README.*

Claude vše připraví; **přístupy pak patří výhradně do `.env`** (je v `.gitignore` — nikdy je nedávej do chatu ani do kódu). Odteď stačí `/google-ads` z libovolného projektu. Detaily: [skill/INSTALL.md](skill/INSTALL.md).

**B) Vlastní automatizace a agentní řešení (pro pokročilé).** Appka je normální CLI stavěné na strojové řízení: `--json` výstupy, mutace defaultně jako validate-only dry-run, vestavěný quota guard (denní limit nevyčerpáš omylem) a QPS retry s back-offem. Vezmi si ji do vlastních skriptů, cronů nebo agentních workflow — kompletní reference příkazů je níže, chování API (quirky, limity) v [docs/api-notes.md](docs/api-notes.md).

## Požadavky

- Python 3.10+
- Google Ads účet + přístupy k API (viz níže — je to složitější než u většiny API, ale jednorázové)

## Instalace

```bash
./setup.sh                # venv + závislosti + .env ze šablony
# → doplň přístupy do .env (viz Autentizace)
./run.sh auth             # jednorázově: OAuth v prohlížeči → refresh token
./run.sh accounts         # první živé čtení = ověření, že vše funguje
```

## Autentizace

Google Ads API potřebuje **čtyři věci v `.env`** (šablona: `.env.example`). Získání krok za krokem:

### 1) Developer token
1. Potřebuješ **MCC (manager) účet** — pokud nemáš, založ zdarma na [ads.google.com/home/tools/manager-accounts](https://ads.google.com/home/tools/manager-accounts).
2. V MCC: **Tools & Settings → Setup → API Center** → požádej o token.
3. Nový token má **Test Account** úroveň — o **Basic Access** (15 000 operací/den na produkční účty) požádáš tamtéž vyplněním formuláře (schválení pár dní).
4. → `GOOGLE_ADS_DEVELOPER_TOKEN`

### 2) OAuth client (Cloud Console)
1. [console.cloud.google.com](https://console.cloud.google.com) → vytvoř/vyber projekt → **APIs & Services → Library** → povol **Google Ads API**.
2. **APIs & Services → OAuth consent screen** → nastav (stačí Testing režim + přidej sebe jako Test user; pozor, v Testing režimu refresh tokeny po ~7 dnech expirují — pro dlouhodobý provoz zvaž Production).
3. **APIs & Services → Credentials → Create credentials → OAuth client ID → Desktop app**.
4. → `GOOGLE_ADS_CLIENT_ID` + `GOOGLE_ADS_CLIENT_SECRET`

### 3) Refresh token
```bash
./run.sh auth    # otevře prohlížeč → přihlas se účtem s přístupem k MCC → vypíše token
```
→ `GOOGLE_ADS_REFRESH_TOKEN`

### 4) MCC login customer ID
ID tvého manager účtu **bez pomlček** → `GOOGLE_ADS_LOGIN_CUSTOMER_ID`

> Všechny čtyři hodnoty jsou hesla k tvým reklamním účtům — patří **výhradně do `.env`** (je v `.gitignore`), nikdy do kódu, gitu ani chatu.

### Multi-account

Libovolnou proměnnou v `.env` můžeš zdvojit se suffixem `_<JMÉNO>` (velkými písmeny) → profil vybereš globálním přepínačem `--account <jméno>`:

```bash
GOOGLE_ADS_REFRESH_TOKEN_KLIENTB=...
GOOGLE_ADS_LOGIN_CUSTOMER_ID_KLIENTB=...
```
```bash
./run.sh --account klientb accounts
```

**Customer ID cílového účtu** je poziční argument většiny příkazů (s pomlčkami i bez — CLI je odstraní). Seznam účtů pod MCC: `./run.sh accounts`.

## Použití

```bash
./run.sh <příkaz> [přepínače]
# ekvivalent: source .venv/bin/activate && python google_ads_cli.py <příkaz> [přepínače]
```

**Konvence napříč CLI:**

- **Peníze v měně účtu** (Kč) — na micros (×1 000 000) převádí CLI samo, oběma směry.
- **`--json`** — strojově čitelný výstup (použij při parsování).
- **Každá mutace je defaultně dry-run** — vypíše plán a přes API `validate_only` ověří proveditelnost, ale **nic nezapíše**. Skutečný zápis až s `--confirm`.
- **REMOVED je trvalé** (Google Ads nemá undelete). Mazání proto vyžaduje entitu ve stavu PAUSED (`--force` obejde) — pauznout si rozmyslíš, smazat už nevrátíš.
- Výpisy defaultně skrývají REMOVED entity (v API zůstávají viditelné navždy).
- Data ve formátu `YYYY-MM-DD`; výkonnostní okna měř radši 60–90 dní (konverzní lag).

### Ochrana účtu (kvóty a rate limity)

- **Denní kvóta**: Basic Access = 15 000 operací/den (čtení request = 1 op bez ohledu na řádky; mutace = 1 op/operace; dry-runy zdarma). CLI trackuje čerpání lokálně v `.quota/` per účet/den (pacifické datum = reset Googlu) a **zastaví se PŘED překročením** (`GOOGLE_ADS_DAILY_OP_CAP` v `.env`; Standard Access limit nemá — nastav vysoko).
- **QPS limity** (per účet + token): při `RESOURCE_EXHAUSTED` CLI čeká 5→10→20 s (respektuje Googlem doporučenou pauzu), max 3 pokusy, pak skončí — nikdy nemlátí do API ve smyčce. Keyword Planner má limit 1 request/s — výzkumy pouštěj sekvenčně.
- Stav: `./run.sh quota`, limity + čerpání: `./run.sh api-limits`.

## Příkazy

### Setup & účet

| Příkaz | Popis |
|--------|-------|
| `auth` | Jednorázový OAuth flow → refresh token |
| `accounts` | Účty pod MCC (ID, název, měna, časové pásmo) |
| `quota` | Dnešní lokální čerpání operací vs. denní cap |
| `api-limits` | Dokumentované limity API + živé lokální čerpání |

### Přehled & reporting

| Příkaz | Popis |
|--------|-------|
| `pulse <cid> [--days N] [--no-compare]` | **Přehled účtu v 5 operacích**: totály, per-kampaň, delty vs. předchozí okno, top movery, optimization score, počet doporučení, policy problémy + varování (rozbité měření, capnuté rozpočty). Výchozí okno 7 dní končící včerejškem |
| `query <cid> --gaql "…"` | Libovolný GAQL dotaz (jádro reportingu) |
| `report <cid> --entity campaign\|ad_group\|keyword --from --to` | Přednastavený výkonnostní report |
| `changes <cid> [--days N] [--sweep]` | Kdo co změnil (≤30 dní, staré→nové, autor); `--sweep` = levný přehled co se hnulo (≤90 dní) |

> **`pulse` spouštěj jako první** při jakémkoli pohledu na účet — nahrazuje řetězení campaigns+report+query a vrací kompaktní digest. Do detailu jdi jen za tím, co pulse vypíchne.

### Výzkum

| Příkaz | Popis |
|--------|-------|
| `keywords-research <cid> --seed "kw1,kw2" [--language] [--geo] [--limit]` | Keyword Planner: hledanost, konkurence, CPC (1 request/s!) |
| `search-terms <cid> --from --to` | Reálné vyhledávací dotazy (zdroj negativ) |

### Kampaně

| Příkaz | Popis |
|--------|-------|
| `campaigns <cid> [--status]` | Výpis search kampaní |
| `campaign-create <cid> --name --budget [--bidding] [--target-cpa] [--target-roas] [--geo] [--language]` | Nová SEARCH kampaň + rozpočet + geo/jazyk atomicky, **startuje PAUSED** (výchozí cílení: ČR + čeština) |
| `campaign-status <cid> <id> --status enabled\|paused\|removed [--force]` | Zapnout / pauznout / smazat (smazání jen z PAUSED!) |
| `bidding-set <cid> <id> --strategy … [--target-cpa] [--target-roas]` | Bidding: `manual_cpc`, `max_conversions`, `max_conversion_value`, `target_cpa`, `target_roas` |
| `campaign-targeting <cid> <id>` | Cílicí kritéria kampaně (geo/jazyk/rozvrh/zařízení/proximity) |

### Rozpočty

| Příkaz | Popis |
|--------|-------|
| `budgets <cid>` | Rozpočty vč. sdílených a Googlem doporučených částek |
| `budget-set <cid> <campaign_id> --amount <Kč>` | Denní rozpočet kampaně (varuje u sdíleného) |
| `budget-create <cid> --name --amount` | Nový **sdílený** rozpočet |
| `budget-assign <cid> --budget-id --campaigns "id1,id2"` | Přepnout kampaně na (sdílený) rozpočet |
| `budget-remove <cid> --budget-id` | Smazat osiřelý rozpočet (bez připojených kampaní) |

### Sestavy & inzeráty

| Příkaz | Popis |
|--------|-------|
| `ad-groups <cid> [--campaign]` | Výpis sestav |
| `ad-group-create <cid> --campaign --name [--cpc]` | Nová sestava |
| `ads <cid> [--ad-group] [--campaign]` | RSA inzeráty: status, **Ad Strength**, approval status |
| `rsa-create <cid> --ad-group --headlines "a\|b\|c" --descriptions "x\|y" --final-url [--path1] [--path2]` | Nová RSA (3–15 headlines ≤30, 2–4 descriptions ≤90). **Preflight lint** hlídá limity a stylové prohřešky před voláním API. Pinning: ` @H1`/`@H2`/`@H3`/`@D1`/`@D2` na konci textu |
| `ad-status <cid> <ad_group_id> <ad_id> --status … [--force]` | Zapnout / pauznout / smazat inzerát (smazání jen z PAUSED) |
| `ad-update-url <cid> <ad_id> --final-url` | Změna Final URL na místě (drží historii; jediné editovatelné pole — texty jsou immutabilní) |
| `ad-policy <cid> [--only-problems] [--campaign] [--ad-group]` | **Kontrola schválení**: approval/review status + policy topics (Google schvaluje asynchronně, ≤1 pracovní den) |

> **Změna textu inzerátu**: texty jsou v API immutabilní → `rsa-create` nová + starou pauznout a smazat (`ad-status`). Status update na REMOVED by tiše neudělal nic — CLI správně používá remove operaci.

### Klíčová slova & negativa

| Příkaz | Popis |
|--------|-------|
| `keywords <cid> [--ad-group] [--campaign]` | Výpis KW s criterion ID (pro remove) |
| `keyword-add <cid> --ad-group --keywords-json '[{"text":"…","match_type":"phrase","cpc":25}]'` | Batch přidání KW (`exact`/`phrase`/`broad`) |
| `keyword-remove <cid> --criteria "agId~critId,…"` | Odebrání KW kritérií |
| `negative-add <cid> --ad-group\|--campaign --keywords "a,b" [--match-type]` | Negativa na sestavu/kampaň |

### Shared sets (sdílené seznamy negativ)

| Příkaz | Popis |
|--------|-------|
| `shared-sets <cid>` | Seznamy + kde jsou připojené |
| `shared-set-create <cid> --name [--type negative-keywords\|account-negatives]` | Nový seznam |
| `shared-set-add <cid> --set --keywords "a,b" [--match-type]` | Naplnění negativy |
| `shared-set-keywords <cid> --set` | Obsah seznamu (criterion ID) |
| `shared-set-remove-keywords <cid> --set --criteria "id1,id2"` | Odebrání ze seznamu |
| `shared-set-attach <cid> --set --campaigns "id1,id2" [--detach]` | Připojení/odpojení kampaním |
| `customer-negatives-attach <cid> --set` | Seznam typu account-negatives na **celý účet** (max 1 000 KW) |
| `customer-negatives-detach <cid> --criterion` | Odpojení account-level negativ (ID vypíše attach) |
| `shared-set-remove <cid> --set` | Smazání celého seznamu (vč. obsahu) |

### Assets (sitelinky, callouts, snippety)

| Příkaz | Popis |
|--------|-------|
| `assets <cid> [--type sitelink\|callout\|snippet]` | Výpis assetů s ID |
| `asset-links <cid>` | Kde je co napojené (účet/kampaň/sestava) |
| `sitelink-create <cid> --sitelinks-json '[{"text":"…","url":"…","desc1":"…","desc2":"…"}]'` | Sitelinky (text ≤25, desc ≤35; pro zobrazení potřebuješ ≥2) |
| `callout-create <cid> --texts "a\|b\|c"` | Callouts (≤25 znaků) |
| `snippet-create <cid> --header Courses --values "a\|b\|c"` | Structured snippet (header z pevného seznamu, 3–10 hodnot ≤25) |
| `asset-link <cid> --asset "id1,id2" --field-type sitelink\|callout\|snippet --campaign\|--ad-group\|--customer` | Napojení assetů |
| `asset-unlink <cid> --asset … --field-type … --campaign\|--ad-group\|--customer` | Odpojení (assety samotné smazat nejde — jsou create-only) |

### Publika / remarketing

| Příkaz | Popis |
|--------|-------|
| `audiences <cid>` | User listy: velikost pro search, eligibility |
| `audience-create <cid> --name --url-contains "…" [--membership-days 30]` | Rule-based list (návštěvníci URL; sbírá web tag) |
| `audiences-attached <cid> [--campaign]` | Co je napojené kde (vč. vyloučení) |
| `audience-attach <cid> --list --campaign\|--ad-group [--mode observation\|targeting] [--bid-modifier]` | Napojení publika. **`observation`** = jen měření/bid (bezpečný default pro search); **`targeting` zúží zobrazování jen na publikum!** |
| `audience-exclude <cid> --list --campaign` | Vyloučení publika z kampaně (např. zákazníci z akvizice) |
| `audience-detach <cid> --criterion --campaign\|--ad-group` | Odpojení |

### Cílení

| Příkaz | Popis |
|--------|-------|
| `geo-suggest --name "Praha,Brno" [--country CZ]` | Vyhledání geo target ID podle názvu |
| `geo-target <cid> <campaign_id> --geo "ids" [--negative] [--proximity "lat,lng,km"] [--remove ids]` | Geo cílení / vyloučení / radius |
| `language-target <cid> <campaign_id> --language "1021" [--remove ids]` | Jazyky (1021=cs, 1034=sk, 1000=en; jen pozitivní) |
| `schedule-set <cid> <campaign_id> --schedule-json '[{"day":"MONDAY","start":8,"end":20,"bid_modifier":1.1}]'` | **Náhrada** celého rozvrhu atomicky (`[]` = 24/7; max 6 bloků/den) |
| `device-bid <cid> <campaign_id> --device mobile --modifier 0.8` | Device bid modifier (0 = na zařízení nezobrazovat) |
| `demographics <cid> [--ad-group]` | Demografická kritéria sestav |
| `demographic-target <cid> --ad-group --value "AGE_RANGE_25_34,MALE" [--negative] [--modifier] [--remove ids]` | Demografie: cílení/vyloučení (věk/pohlaví/příjem) |

> ⚠️ Kampaň bez geo a jazykových kritérií běží na **celý svět ve všech jazycích**. `campaign-create` proto cílení nastavuje defaultně; po ručních zásazích ověř přes `campaign-targeting`.

### Konverzní akce

| Příkaz | Popis |
|--------|-------|
| `conversions <cid>` | Výpis: status, kategorie, **primary/secondary**, counting |
| `conversion-create <cid> --name --category PURCHASE\|LEAD\|… [--primary] [--counting one\|many] [--value]` | Nová WEBPAGE akce (měřit ji musí tag/GTM!) |
| `conversion-update <cid> <id> [--status] [--primary yes\|no] [--counting] [--value]` | Úprava akce |

> `metrics.conversions` počítá jen **primary** akce (na ně optimalizuje Smart Bidding); `all_conversions` všechno. `pulse` automaticky varuje, když je primary 0 a all nenulové (typicky špatně nastavená akce).

### Doporučení Googlu

| Příkaz | Popis |
|--------|-------|
| `recommendations <cid>` | Výpis s typem, dopadem, resource name |
| `recommendation-apply <cid> --resource "…"` | Aplikace (jak ji navrhuje Google; vlastní hodnoty radši přes `budget-set` apod.) |
| `recommendation-dismiss <cid> --resource "…"` | Zamítnutí (přestane srážet optimization score) |

> Resource names doporučení se regenerují (denně i častěji) — vypiš a aplikuj/zamítni v jedné session.

### Štítky

| Příkaz | Popis |
|--------|-------|
| `labels <cid>` / `label-create <cid> --name [--description] [--color]` | Výpis / tvorba |
| `label-assign` / `label-unassign <cid> --label <id> --campaign\|--ad-group\|--ad "agId~adId"\|--keyword "agId~critId"` | Přiřazení / sundání |
| `label-remove <cid> --label <id>` | Smazání štítku (vč. všech přiřazení) |

### DSA (Dynamic Search Ads)

| Příkaz | Popis |
|--------|-------|
| `dsa-setting <cid> <campaign_id> --domain aifirst.cz [--language-code cs]` | DSA nastavení kampaně |
| `dsa-ad-group-create <cid> --campaign --name [--cpc]` | DSA sestava (bez keywords a RSA!) |
| `dsa-create <cid> --ad-group --descriptions "a\|b"` | DSA inzerát (headline+URL generuje Google) |
| `webpage-targets <cid> --ad-group` | Webpage kritéria sestavy |
| `webpage-target-add <cid> --ad-group --name --conditions "url:blog,title:kurz" [--negative] [--cpc]` | Cílení na stránky (≤3 AND podmínky; bez podmínek = celý web) |
| `webpage-target-remove <cid> --criteria "agId~critId"` | Odebrání |

### Performance Max (jen reporting)

| Příkaz | Popis |
|--------|-------|
| `pmax <cid> --from --to [--channels]` | Metriky PMax kampaní (`--channels` = rozpad po sítích) |
| `pmax-search-terms <cid> --from --to [--campaign]` | Search terms PMax kampaní |

### Experimenty

| Příkaz | Popis |
|--------|-------|
| `experiments <cid>` | Výpis experimentů |
| `experiment-create <cid> --campaign --name --start --end [--traffic-split 50]` | SEARCH_CUSTOM experiment + arms; vygeneruje **draft kampaň** k úpravě |
| `experiment-schedule <cid> <id>` | Spuštění (async; start plánuj do budoucna kvůli review inzerátů) |
| `experiment-results <cid> <id>` | Výsledky: treatment vs. control |
| `experiment-end <cid> <id>` | Ukončení bez aplikace změn |
| `experiment-promote <cid> <id>` | Propsání treatment změn do základní kampaně |

## Skill pro Claude Code (`/google-ads`)

V `skill/google-ads/` je přibalený skill, který z appky dělá „agenta na Google Ads": scénáře (research → create → optimize → policy-check → negatives → audiences), bezpečnostní pravidla (plán → schválení → `--confirm`, PAUSED start, kvóty) a pravidla psaní inzerátů. Instalace: **[skill/INSTALL.md](skill/INSTALL.md)** (kopie do `~/.claude/skills/` + nastavení cesty).

## Dokumentace

- **[docs/api-notes.md](docs/api-notes.md)** — jak se Google Ads API reálně chová (immutabilita, kvóty, quirky, composite resource names)
- **[CHANGELOG.md](CHANGELOG.md)** — historie verzí (odebírej přes Watch → Custom → Releases)
- **[CLAUDE.md](CLAUDE.md)** — orientace v kódu pro coding agenty
