# Google Ads App

[🇬🇧 English](README.md) · **🇨🇿 Čeština** · [🇪🇸 Español](i18n/README.es.md) · [🇧🇷 Português](i18n/README.pt-BR.md) · [🇩🇪 Deutsch](i18n/README.de.md) · [🇫🇷 Français](i18n/README.fr.md) · [🇨🇳 简体中文](i18n/README.zh-CN.md) · [🇯🇵 日本語](i18n/README.ja.md) · [🇸🇪 Svenska](i18n/README.sv.md) · [🇳🇴 Norsk](i18n/README.nb.md) · [🇩🇰 Dansk](i18n/README.da.md)

CLI aplikace pro správu **search kampaní na Google Ads** přes oficiální [Google Ads API](https://developers.google.com/google-ads/api) (v25, knihovna `google-ads` 35+). Pro marketéry a foundery, kteří chtějí kampaně spravovat z terminálu nebo je svěřit Claude Code místo klikání ve webovém rozhraní Google Ads.

Pokrývá celý životní cyklus search kampaní: kampaně, sestavy, RSA inzeráty, klíčová slova, negativa (vč. sdílených seznamů), assety (sitelinky/callouts/snippety), publika a remarketing, cílení (geo/jazyk/rozvrh/zařízení/demografie), rozpočty, Smart Bidding, konverzní akce, doporučení Googlu, kontrolu schválení inzerátů, change history, experimenty a GAQL reporting. Display/YouTube/Shopping neřeší; Performance Max jen reportuje.

Autor: [Jindřich Fáborský](https://www.faborsky.cz) · kurz [AI First](https://aifirst.cz)

> [!TIP]
> **Appka je zdarma a je tvoje.** Naklonuj si ji, používej ji, přestav si ji po svém.
>
> Nevíš, jak ji rozjet? Nebo chceš AI v marketingu používat systematicky: řídit z jednoho místa všechny kanály, automatizovat rutinu, postavit si vlastní znalostní bázi a vibe codovat si nástroje na míru své firmě? To učím v kurzu **[AI First](https://aifirst.cz)**. Tahle appka je v něm vysvětlená i s tím, jak si postavit vlastní.

Součástí repa je i [skill pro Claude Code](#skill-pro-claude-code-google-ads), který appku obaluje.

## 🆕 Co je nového

Aktuální verze **2.3.0**: **developer token už není potřeba** (Google developer tokeny 9. 9. 2026 zrušil, přístupová úroveň teď patří Cloud projektu a návod níže je na to přepsaný), knihovna 35 (API zůstává v25), `bidding-set --portfolio` připojí kampaň k portfolio strategii, `campaign-create --no-search-partners` / `--presence-only`, opravy pro **Windows** (venv v Git Bash, UTF-8 výstup přes rouru) a srozumitelnější hlášky pro Explorer access a nové účty pod MCC. Díky přispěvatelům, kteří to nahlásili a poslali.

2.2.0, **audit před zveřejněním**: API přepnuto na **v25** (knihovna 31.4), **opravené tiché no-op updaty** (`bidding-set max_conversions`/`manual_cpc`, `device-bid --modifier 0` a `conversion-update --primary no` dřív neudělaly nic, protože update maska vynechávala pole nastavená na výchozí hodnotu), **kvóta měřená klouzavě za 24 h** (jak ji měří Google; ne po kalendářních dnech), `./run.sh auth` **zapisuje refresh token rovnou do `.env`** (token už nejde přes terminál ani chat), **service account** jako alternativa OAuth (bez prohlížeče, bez 7denní expirace), čisté chybové hlášky místo tracebacků (expirovaný token, neschválený developer token…), `--json` funguje i za příkazem, konec hardcoded `LIMIT 500` v `pmax-search-terms`, **offline testovací sada (107 testů)** validující každý zápis proti reálným typům API v25, MIT licence. Předtím 2.1.0 (vizuální podpis) a 2.0.0 (velký refresh 19 → **85 příkazů**). Celá historie: **[CHANGELOG.md](CHANGELOG.md)**.

> 💡 Chceš dostávat upozornění na nové verze? Na GitHubu: **Watch → Custom → Releases**.

## Dva způsoby, jak appku používat

**A) Orchestrace přes Claude Code (výchozí a nejjednodušší).** Appku řídí Claude Code (nebo jiný coding agent) přes přibalený skill. Zadáváš cíle česky, agent volá CLI, drží bezpečnostní pravidla (plán → schválení → zápis, dry-run default, kvóty, „REMOVED je trvalé“) a zná quirky API. Nejrychlejší start: otevři Claude Code a vlož mu prompt typu:

> *Naklonuj https://github.com/faborsky/google-ads-app, spusť `./setup.sh`, nainstaluj mi přibalený skill podle `skill/INSTALL.md` a pak mě provoď získáním přístupů do `.env` podle README (sekce Autentizace).*

Claude vše připraví; **přístupy pak patří výhradně do `.env`** (je v `.gitignore`, nikdy je nedávej do chatu ani do kódu). Odteď stačí `/google-ads` z libovolného projektu. Detaily: [skill/INSTALL.md](skill/INSTALL.md).

**B) Vlastní automatizace a agentní řešení (pro pokročilé).** Appka je normální CLI stavěné na strojové řízení: `--json` výstupy, mutace defaultně jako validate-only dry-run, vestavěný quota guard (denní limit nevyčerpáš omylem) a QPS retry s back-offem. Vezmi si ji do vlastních skriptů, cronů nebo agentních workflow. Kompletní reference příkazů je níže, chování API (quirky, limity) v [docs/api-notes.md](docs/api-notes.md). Pro bezobslužný provoz použij **service account** (viz [Autentizace](#autentizace)), ten nemá co expirovat.

## Požadavky

- Python 3.10–3.14 (knihovna `google-ads` zatím nepodporuje 3.15)
- Google Ads účet + přístupy k API (viz níže; je to složitější než u většiny API, ale jednorázové)

## Instalace

```bash
./setup.sh                # venv + závislosti + .env ze šablony (chmod 600)
# → doplň přístupy do .env (viz Autentizace)
./run.sh auth             # jednorázově: OAuth v prohlížeči → refresh token se zapíše do .env
./run.sh accounts         # první živé čtení = ověření, že vše funguje
```

Jiný Python než výchozí `python3`: `PYTHON=python3.12 ./setup.sh`.

### Windows

Skripty `setup.sh`/`run.sh` jsou bashové. Na Windows použij **Git Bash** (součást [Git for Windows](https://git-scm.com/download/win)) nebo **WSL**; skripty najdou venv v `.venv/bin` i `.venv/Scripts`. `python3` bývá na Windows jen alias Microsoft Store, takže setup spusť jako `PYTHON=python ./setup.sh`. CLI vždy píše UTF-8, takže výstup přes rouru (tak ho čte Claude Code) má diakritiku i šipky v pořádku. Alternativně čistý PowerShell:

```powershell
git clone https://github.com/faborsky/google-ads-app.git; cd google-ads-app
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # vyplň přístupy
python google_ads_cli.py auth
python google_ads_cli.py accounts
```

## Autentizace

Google Ads API je na přístupy nejpřísnější z velkých reklamních API: potřebuješ schválenou **přístupovou úroveň Google Cloud projektu** (= „smíš volat API“), **OAuth přístup k účtu** (= „smíš sahat na tyhle účty“) a **MCC ID**. Všechno je jednorázové. Ověřeno proti oficiální dokumentaci 2026-11-01 ([access levels](https://developers.google.com/google-ads/api/docs/api-policy/access-levels), [konec developer tokenů](https://developers.google.com/google-ads/api/docs/api-policy/developer-token)).

> **Developer tokeny skončily.** Google je zrušil **9. 9. 2026**: přístupová úroveň (Explorer / Basic / Standard) teď patří Cloud projektu a API token ignoruje. Od verze 2.3.0 appka `GOOGLE_ADS_DEVELOPER_TOKEN` nepotřebuje; stará hodnota v `.env` ničemu nevadí.

### Přehled: co všechno do `.env`

Tři hodnoty vyplníš ručně, čtvrtou si appka zapíše sama a **jedno číslo do `.env` vůbec nepatří**:

| Proměnná | Co to je | Kde vzít | Jak se tam dostane |
|---|---|---|---|
| `GOOGLE_ADS_CLIENT_ID` | OAuth klient, končí `.apps.googleusercontent.com` | Google Cloud Console (krok 2) | zkopíruješ ručně |
| `GOOGLE_ADS_CLIENT_SECRET` | heslo toho OAuth klienta | Google Cloud Console (krok 2) | zkopíruješ ručně |
| `GOOGLE_ADS_REFRESH_TOKEN` | dlouhodobý přístup k tvému Google účtu | `./run.sh auth` (krok 3) | **zapíše se samo**, nikam ho nekopíruješ |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | ID MCC **bez pomlček** (`123-456-7890` → `1234567890`) | hlavička Google Ads (krok 4) | zkopíruješ ručně |
| `GOOGLE_ADS_DAILY_OP_CAP` | strop operací za 24 h | podle přístupové úrovně Cloud projektu (krok 1) | `15000` (Basic) / `2880` (Explorer) |
| (žádná) | **customer ID cílového účtu**, se kterým pracuješ | `./run.sh accounts` | **do `.env` nepatří**, je to argument příkazu |

Tři čísla, která se snadno pletou: **Client ID** (dlouhý řetězec z Cloudu) × **MCC login customer ID** (10 číslic, do `.env`) × **customer ID klientského účtu** (10 číslic, do příkazu).

Alternativa ke kroku 2+3 bez prohlížeče: **service account** (níže).

### 0) Passkey: udělej to dřív, než začneš

Od **5. 8. 2026** chce Google při generování nového refresh tokenu (krok 3) ověření passkey. Existujících tokenů se to netýká.

Podívej se na **[myaccount.google.com/signinoptions/passkeys](https://myaccount.google.com/signinoptions/passkeys)** (pozor, `g.co/passkeys` vede jen na marketingovou stránku). Google je zakládá i sám (Android, iCloud Keychain, profil v Chrome), takže tam nejspíš nějakou máš a nemusíš nic dělat. Když ne, založ ji **hned teď, ještě před vším ostatním**. Je to otázka půl minuty.

Jediný případ, kdy to nejde vyřešit na počkání: nemáš-li na účtu žádnou jinou passkey, kterou by šla ta nová schválit, může ji Google až týden držet jako nedůvěryhodnou. Pak dokonči zbytek nastavení a `auth` spusť, až projde, nebo rovnou použij service account.

Passkey není biometrie. Bez čtečky otisků ji potvrdíš telefonem přes QR kód, heslem k počítači, PINem z Windows Hello nebo správcem hesel (Bitwarden, 1Password). Kdo to nechce řešit vůbec, jde cestou **service accountu** (níže), ten je z požadavku vyjmutý.

### 1) Manager účet + přístupová úroveň (Cloud projekt)

1. Potřebuješ **manager (MCC) účet**. Pokud nemáš, založ ho zdarma na [ads.google.com/home/tools/manager-accounts](https://ads.google.com/home/tools/manager-accounts) (e-mailem, který ještě nemá Google Ads účet) a propoj pod něj reklamní účty.
2. Založ Google Cloud projekt (nebo použij existující) a **povol v něm Google Ads API**: [console.cloud.google.com/apis/library/googleads.googleapis.com](https://console.cloud.google.com/apis/library/googleads.googleapis.com) → **Enable**. Projekt tím dostane *Test* přístup (jen testovací účty).
3. O vyšší úroveň požádej na stránce **Google Ads API Overview**: [console.cloud.google.com/google/ads-apis/overview](https://console.cloud.google.com/google/ads-apis/overview) (vyber projekt). Potřebuješ na projektu roli Owner, Editor, Quota Administrator nebo Service Usage Admin. Staré *Tools → API Center* v Google Ads už nic nevydává.

   | Úroveň | Na které účty | Denní limit operací | Jak ji získat |
   |---|---|---|---|
   | Test (automaticky po povolení API) | jen [testovací účty](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts) | 15 000 | produkční účet vrátí `CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION` |
   | **Explorer** | testovací i **produkční** | 2 880 / den na produkčních | požádej na stránce Overview, schválení bývá automatické. **Keyword Planner zablokovaný** (`keywords-research` nejede), jinak všechno z tohohle CLI funguje. Nastav `GOOGLE_ADS_DAILY_OP_CAP=2880`. |
   | **Basic** | testovací i produkční | **15 000 / den** | z Exploreru: Overview → *Upgrade access level* → *Apply for access*. Předtím je **povinné [ověření značky](https://developers.google.com/google-ads/api/docs/api-policy/brand-verification) (brand verification) Cloud projektu**; pak schválení trvá minuty. Vše vč. Keyword Planneru. |
   | Standard | testovací i produkční | bez limitu | pro velké nástroje |

   Limit se měří **klouzavě za posledních 24 h** (ne kalendářní den). CLI ho hlídá lokálně a zastaví se před překročením (`GOOGLE_ADS_DAILY_OP_CAP` v `.env`). Známý problém na straně Googlu: ověření značky odmítá projekty na free trialu nebo s pozastavenou fakturací.

### 2) OAuth klient (Cloud Console)

Nastavení OAuth se v Cloud Console přesunulo pod **Google Auth Platform**. Starší návody (i verze tohohle README do 2.2.0) posílají na „APIs & Services → OAuth consent screen“, což už neexistuje. Aktuální cesty, ověřeno 28. 8. 2026:

1. Použij **stejný Cloud projekt** jako v kroku 1 (ten s přístupovou úrovní a povoleným Google Ads API).
2. **Branding**: [console.cloud.google.com/auth/branding](https://console.cloud.google.com/auth/branding), název aplikace (uvidíš ho na přihlašovací obrazovce), support e-mail, kontakt na vývojáře.
3. **Audience**: [console.cloud.google.com/auth/audience](https://console.cloud.google.com/auth/audience), User type **External** a Publishing status přes **Publish app** na **In production**. V režimu „Testing“ Google **refresh tokeny zneplatňuje po 7 dnech** a musel/a bys `auth` opakovat každý týden.
4. **Clients**: [console.cloud.google.com/auth/clients](https://console.cloud.google.com/auth/clients) → **+ Create client** → Application type **Desktop app** → po vytvoření vyskočí obě hodnoty.
5. → `GOOGLE_ADS_CLIENT_ID` + `GOOGLE_ADS_CLIENT_SECRET`

Scopes ručně přidávat netřeba. Appka zůstane „neověřená“ (Google při přihlášení ukáže *Google hasn't verified this app* → *Advanced → Go to …*). Pro vlastní nástroj je to v pořádku, ověřením procházet nemusíš.

### 3) Refresh token

```bash
./run.sh auth    # otevře prohlížeč → přihlas se účtem s přístupem k MCC → token se ZAPÍŠE do .env
```

Token se nikde nevypisuje (záloha původního `.env` v `.env.bak`, oba `chmod 600`). Chceš ho jen vypsat a uložit si ho sám? `./run.sh auth --print`. Pro pojmenovaný profil `./run.sh --account klientb auth` zapíše `GOOGLE_ADS_REFRESH_TOKEN_KLIENTB`.

> Když CLI hlásí `invalid_grant`: token expiroval (consent screen v „Testing“) nebo byl odvolán → spusť `./run.sh auth` znovu.

### 4) MCC login customer ID

ID tvého manager účtu **bez pomlček** → `GOOGLE_ADS_LOGIN_CUSTOMER_ID`. Cílový klientský účet (customer ID) je pak poziční argument příkazů.

### Alternativa: service account (pro automatizace, bez prohlížeče)

Google Ads API umí ověřit **service account přímo**, bez Workspace i bez domain-wide delegation:

1. Cloud Console → **IAM & Admin → Service Accounts → Create** → vytvoř klíč (**JSON**) a ulož ho mimo repo nebo do gitignorované složky `.secrets/`.
2. V Google Ads (MCC nebo přímo účet) → **Admin → Access and security → Users → +** → zadej e-mail service accountu a dej mu roli (Standard stačí na správu kampaní).
3. V `.env`: `GOOGLE_ADS_JSON_KEY_FILE_PATH=.secrets/service-account.json` (+ `GOOGLE_ADS_DEVELOPER_TOKEN` a `GOOGLE_ADS_LOGIN_CUSTOMER_ID`). `CLIENT_ID/SECRET/REFRESH_TOKEN` pak nejsou potřeba. Volitelně `GOOGLE_ADS_IMPERSONATED_EMAIL` pro Workspace delegaci.

Výhody: nic neexpiruje, přístup nevisí na tvém osobním loginu, hodí se pro crony a agenty. Klíč je heslo, nikdy ho nedávej do gitu.

> Všechny hodnoty v `.env` jsou hesla k tvým reklamním účtům. Patří **výhradně do `.env`** (je v `.gitignore`), nikdy do kódu, gitu ani chatu.

### Testovací účet (volitelný sandbox)

Chceš si API zkoušet bez rizika? Založ [testovací manager účet](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts) (jiným Google účtem než produkční MCC), pod ním testovací klientský účet, a volej ho se **stejným Cloud projektem a OAuth klientem** (stačí tam Test přístup). Testovací účty nic neservírují a neúčtují; po roce nečinnosti je Google maže.

### Multi-account

Libovolnou proměnnou v `.env` můžeš zdvojit se suffixem `_<JMÉNO>` (velkými písmeny) → profil vybereš globálním přepínačem `--account <jméno>`:

```bash
GOOGLE_ADS_REFRESH_TOKEN_KLIENTB=...
GOOGLE_ADS_LOGIN_CUSTOMER_ID_KLIENTB=...
```
```bash
./run.sh --account klientb accounts
```

**Customer ID cílového účtu** je poziční argument většiny příkazů (s pomlčkami i bez, CLI je odstraní). Seznam účtů pod MCC (celá hierarchie): `./run.sh accounts`.

## Použití

```bash
./run.sh <příkaz> [přepínače]
# ekvivalent: source .venv/bin/activate && python google_ads_cli.py <příkaz> [přepínače]
```

**Konvence napříč CLI:**

- **Peníze v měně účtu** (Kč). Na micros (×1 000 000) převádí CLI samo, oběma směry.
- **`--json`**: strojově čitelný výstup (použij při parsování; funguje před i za názvem příkazu).
- **Každá mutace je defaultně dry-run**: vypíše plán a přes API `validate_only` ověří proveditelnost, ale **nic nezapíše**. Skutečný zápis až s `--confirm`.
- **REMOVED je trvalé** (Google Ads nemá undelete). Mazání proto vyžaduje entitu ve stavu PAUSED (`--force` obejde). Pauznout si rozmyslíš, smazat už nevrátíš.
- Výpisy defaultně skrývají REMOVED entity (v API zůstávají viditelné navždy) a **nikdy neusekávají data**: `search_stream` vrací vše; kde výstup zkracuje `--limit`, CLI to řekne.
- Data ve formátu `YYYY-MM-DD`; výkonnostní okna měř radši 60–90 dní (konverzní lag).

### Ochrana účtu (kvóty a rate limity)

- **Denní kvóta**: Basic Access = 15 000 operací (Explorer 2 880) **klouzavě za 24 h** na přístupovou úroveň Cloud projektu (čtení request = 1 op bez ohledu na řádky; mutace = 1 op/operace; validate_only dry-runy počítáme taky, protože Google výjimku nedokumentuje, takže lokální odhad je vždy ≥ realita). CLI trackuje čerpání lokálně v `.quota/` per účet a **zastaví se PŘED překročením** (`GOOGLE_ADS_DAILY_OP_CAP` v `.env`; Standard Access limit nemá, nastav vysoko).
- **QPS limity** (token bucket per účet + token): při `RESOURCE_EXHAUSTED` CLI čeká 5→10→20 s (respektuje Googlem doporučenou pauzu), max 3 pokusy, pak skončí. Nikdy nemlátí do API ve smyčce. Přechodné výpadky (UNAVAILABLE) opakuje jen u **čtení**; zápis mohl projít, ten se nikdy neopakuje. Keyword Planner má limit 1 request/s, výzkumy pouštěj sekvenčně.
- Stav: `./run.sh quota`, limity + čerpání: `./run.sh api-limits`.

## Příkazy

### Setup & účet

| Příkaz | Popis |
|--------|-------|
| `auth [--print]` | Jednorázový OAuth flow → refresh token **zapíše do `.env`** (`--print` ho místo toho vypíše) |
| `accounts` | Celá hierarchie účtů pod MCC (ID, název, měna, časové pásmo, úroveň) |
| `quota` | Lokální čerpání operací za posledních 24 h vs. cap |
| `api-limits` | Dokumentované limity API (verze, úrovně přístupu, okna) + živé lokální čerpání |

### Přehled & reporting

| Příkaz | Popis |
|--------|-------|
| `pulse <cid> [--days N] [--no-compare]` | **Přehled účtu v 5 operacích**: totály, per-kampaň, delty vs. předchozí okno, top movery, optimization score, počet doporučení, policy problémy + varování (rozbité měření, capnuté rozpočty). Výchozí okno 7 dní končící včerejškem |
| `query <cid> --gaql "…"` | Libovolný GAQL dotaz (jádro reportingu) |
| `report <cid> --entity campaign\|ad_group\|keyword --from --to` | Přednastavený výkonnostní report |
| `changes <cid> [--days N] [--sweep] [--limit N]` | Kdo co změnil (≤30 dní, staré→nové, autor); `--sweep` = levný přehled co se hnulo (≤90 dní). API tu LIMIT vyžaduje (default 200, max 10 000); když výsledek narazí na limit, CLI upozorní |

> **`pulse` spouštěj jako první** při jakémkoli pohledu na účet. Nahrazuje řetězení campaigns+report+query a vrací kompaktní digest. Do detailu jdi jen za tím, co pulse vypíchne.

### Výzkum

| Příkaz | Popis |
|--------|-------|
| `keywords-research <cid> --seed "kw1,kw2" [--language] [--geo] [--limit]` | Keyword Planner: hledanost, konkurence, CPC (1 request/s!). **Vyžaduje Basic Access**, na Explorer úrovni je KeywordPlanIdeaService zablokovaná |
| `search-terms <cid> --from --to` | Reálné vyhledávací dotazy (zdroj negativ) |

### Kampaně

| Příkaz | Popis |
|--------|-------|
| `campaigns <cid> [--status]` | Výpis search kampaní |
| `campaign-create <cid> --name --budget [--bidding] [--target-cpa] [--target-roas] [--geo] [--language] [--no-search-partners] [--presence-only]` | Nová SEARCH kampaň + rozpočet + geo/jazyk atomicky, **startuje PAUSED** (výchozí cílení: ČR + čeština; partneři Vyhledávací sítě zapnutí a „přítomnost nebo zájem“, pokud je nevypneš) |
| `campaign-status <cid> <id> --status enabled\|paused\|removed [--force]` | Zapnout / pauznout / smazat (smazání jen z PAUSED!) |
| `bidding-set <cid> <id> --strategy … [--target-cpa] [--target-roas]` | Bidding: `manual_cpc`, `max_conversions`, `max_conversion_value`, `target_cpa`, `target_roas` |
| `bidding-set <cid> <id> --portfolio <bidding_strategy_id>` | Připojit kampaň k existující portfolio strategii (cíl se nastavuje na portfoliu) |
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
| `ad-update-url <cid> <ad_id> --final-url` | Změna Final URL na místě (drží historii; jediné editovatelné pole, texty jsou immutabilní) |
| `ad-policy <cid> [--only-problems] [--campaign] [--ad-group]` | **Kontrola schválení**: approval/review status + policy topics (Google schvaluje asynchronně, ≤1 pracovní den) |

> **Změna textu inzerátu**: texty jsou v API immutabilní → `rsa-create` nová + starou pauznout a smazat (`ad-status`). Status update na REMOVED by tiše neudělal nic, CLI proto používá remove operaci.

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
| `customer-negatives-attach <cid> --set` | Seznam typu account-negatives na **celý účet** (max 1 000 KW) |
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
| `asset-unlink <cid> --asset … --field-type … --campaign\|--ad-group\|--customer` | Odpojení (assety samotné smazat nejde, jsou create-only) |

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
| `conversion-create <cid> --name --category PURCHASE\|SUBMIT_LEAD_FORM\|… [--primary] [--counting one\|many] [--value]` | Nová WEBPAGE akce (měřit ji musí tag/GTM!) |
| `conversion-update <cid> <id> [--status] [--primary yes\|no] [--counting] [--value]` | Úprava akce |

> `metrics.conversions` počítá jen **primary** akce (na ně optimalizuje Smart Bidding); `all_conversions` všechno. `pulse` automaticky varuje, když je primary 0 a all nenulové (typicky špatně nastavená akce).

### Doporučení Googlu

| Příkaz | Popis |
|--------|-------|
| `recommendations <cid>` | Výpis s typem, dopadem, resource name |
| `recommendation-apply <cid> --resource "…"` | Aplikace (jak ji navrhuje Google; vlastní hodnoty radši přes `budget-set` apod.) |
| `recommendation-dismiss <cid> --resource "…"` | Zamítnutí (přestane srážet optimization score) |

> Resource names doporučení se regenerují (denně i častěji), takže vypiš a aplikuj/zamítni v jedné session.

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
| `pmax-search-terms <cid> --from --to [--campaign] [--limit N]` | Search terms PMax kampaní (vše; `--limit` jen zkrátí výpis a řekne to) |

### Experimenty

| Příkaz | Popis |
|--------|-------|
| `experiments <cid>` | Výpis experimentů |
| `experiment-create <cid> --campaign --name --start --end [--traffic-split 50]` | SEARCH_CUSTOM experiment + arms; vygeneruje **draft kampaň** k úpravě |
| `experiment-schedule <cid> <id>` | Spuštění (async; start plánuj do budoucna kvůli review inzerátů) |
| `experiment-results <cid> <id>` | Výsledky: treatment vs. control |
| `experiment-end <cid> <id>` | Ukončení bez aplikace změn |
| `experiment-promote <cid> <id>` | Propsání treatment změn do základní kampaně |

## Příklady

```bash
# Přehled účtu za posledních 7 dní (vs. předchozích 7) — první krok každé analýzy
./run.sh pulse 123-456-7890

# Výzkum klíčových slov (Basic Access; 1 request/s)
./run.sh keywords-research 1234567890 --seed "kurz ai,ai školení" --limit 50

# Sestavení kampaně shora dolů — každý krok nejdřív dry-run, pak --confirm
./run.sh campaign-create 1234567890 --name "AI kurzy – Search" --budget 500 --bidding max_conversions
./run.sh campaign-create 1234567890 --name "AI kurzy – Search" --budget 500 --bidding max_conversions --confirm
./run.sh ad-group-create 1234567890 --campaign 111 --name "Kurz AI" --cpc 20 --confirm
./run.sh keyword-add 1234567890 --ad-group 222 \
  --keywords-json '[{"text":"kurz ai","match_type":"phrase","cpc":25},{"text":"ai školení","match_type":"exact"}]' --confirm
./run.sh rsa-create 1234567890 --ad-group 222 \
  --headlines "AI First @H1|Kurz AI pro marketéry|Začni ještě dnes|Praktické AI v práci" \
  --descriptions "Naučte se AI využívat v každodenní praxi.|Videokurz, který šetří hodiny práce." \
  --final-url "https://aifirst.cz" --confirm
./run.sh negative-add 1234567890 --campaign 111 --keywords "zdarma,free,práce" --confirm
./run.sh campaign-targeting 1234567890 111        # ověř geo + jazyk před zapnutím
./run.sh ad-policy 1234567890 --only-problems     # po schválení inzerátů

# Vypnout kampaň na tabletech, omezit rozvrh
./run.sh device-bid 1234567890 111 --device tablet --modifier 0 --confirm
./run.sh schedule-set 1234567890 111 --schedule-json '[{"day":"MONDAY","start":8,"end":20}]' --confirm

# Reporting pro další zpracování
./run.sh report 1234567890 --entity keyword --from 2026-06-01 --to 2026-08-20 --json
./run.sh search-terms 1234567890 --from 2026-06-01 --to 2026-08-20 --json
```

## Skill pro Claude Code (`/google-ads`)

V `skill/google-ads/` je přibalený skill, který z appky dělá „agenta na Google Ads“: scénáře (research → create → optimize → policy-check → negatives → audiences), bezpečnostní pravidla (plán → schválení → `--confirm`, PAUSED start, kvóty) a pravidla psaní inzerátů. Instalace: **[skill/INSTALL.md](skill/INSTALL.md)** (kopie do `~/.claude/skills/` + nastavení cesty).

Skill ti dává **mechaniku** (jak věci udělat nástrojem) a **pravidla** (co Google povoluje). Strategii průběžné optimalizace si nastavíš podle cílů firmy.

## Testy

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

Sada běží **kompletně offline, bez přístupů**: každý zápisový příkaz staví operace proti reálným proto typům API v25 (překlep v názvu pole/enumu = červený test), gRPC volání nahrazuje recorder. Pokrývá dry-run default, pojistku PAUSED-před-REMOVED, klouzavou kvótu, retry politiku, presence-aware update masky, lint, zápis tokenu do `.env` a první kontakt přes CLI (`--help`, `--json`, chybové cesty bez tracebacku).

## Struktura projektu

```
google-ads-app/
├── google_ads_cli.py   # Tenký entrypoint (volá gads.cli.main)
├── gads/               # Balík s implementací
│   ├── api.py          #   engine: .env + účty, klient (pin API verze), quota guard, retry, query/mutation runnery
│   ├── formatting.py   #   micros⇄Kč, JSON výstup, chyby
│   ├── lint.py         #   preflight lint textů (RSA/assety)
│   ├── cli.py          #   argparse + dispatch (_cmd = parser + handler v jednom)
│   └── commands/       #   jeden modul na doménu (campaigns, ads, keywords, …)
├── tests/              # Offline pytest sada (117 testů)
├── scripts/check_docs_consistency.py   # CLI ↔ README ↔ CLAUDE.md ↔ skill
├── requirements.txt · requirements-dev.txt
├── setup.sh · run.sh   # Instalační / spouštěcí skript (aktivuje venv)
├── .env.example        # Šablona přístupů
├── CLAUDE.md           # Signpost pro Claude Code (+ dokumentační mapa)
├── docs/api-notes.md   # Hutná reference chování Google Ads API
├── CHANGELOG.md        # Historie verzí
├── .env                # Přístupy (NEVERZOVAT)
└── skill/              # Skill pro Claude Code (/google-ads) + INSTALL.md
```

## Dokumentace

- **[docs/api-notes.md](docs/api-notes.md)**: jak se Google Ads API chová v praxi (verze, přístupové úrovně, kvóty, immutabilita, quirky, composite resource names)
- **[CHANGELOG.md](CHANGELOG.md)**: historie verzí (odebírej přes Watch → Custom → Releases)
- **[CLAUDE.md](CLAUDE.md)**: orientace v kódu pro coding agenty

## Chyby a náměty

Něco nefunguje nebo chybí? Založ **GitHub Issue**. Pull requesty vítány. Repo je primárně výukové, drž se stylu okolního kódu a přilož test.

## Licence

[MIT](LICENSE) © 2026 Jindřich Fáborský

## Autor

[Jindřich Fáborský](https://www.faborsky.cz), marketér a lektor. Vibe coding a AI v marketingu učím v kurzu [AI First](https://aifirst.cz).

Google Ads App je doprovodný materiál k 7. lekci kurzu, která ukazuje, jak si vibe codingem postavit nástroje na každodenní marketingovou práci a ušetřit hodiny rutiny. Další appky pro foundery a marketéry najdeš na **[faborsky.cz/appky](https://www.faborsky.cz/appky)**.
