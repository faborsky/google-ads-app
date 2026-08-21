# Instalace skillu `/google-ads` do Claude Code

Tahle složka obsahuje **skill pro Claude Code**, který obaluje CLI aplikaci v tomhle repu a přidává pravidla práce s Google Ads (bezpečnostní zábradlí, RSA pravidla, struktura kampaní, scénáře). Po instalaci ho v Claude Code vyvoláš jako `/google-ads`.

> Skill bez aplikace nefunguje — nejdřív zprovozni samotnou appku podle hlavního `README.md` (`./setup.sh` + přístupy v `.env` + `./run.sh auth`, který refresh token do `.env` zapíše sám).

## Předpoklady

1. **Naklonovaný tenhle repozitář** a funkční appka (`./run.sh accounts` vrací tvoje účty).
2. Nainstalovaný **Claude Code**.

> Získání přístupů (developer token + jeho přístupová úroveň, OAuth klient nebo service account, MCC ID) je u Google Ads složitější než u většiny API — krok za krokem to popisuje hlavní `README.md` → Autentizace. Všechny přístupy patří **výhradně do `.env`** (je v `.gitignore`) — nikdy do kódu, gitu ani chatu; ani Claudovi je neposílej, `auth` je uloží sám.

## Krok za krokem

Předpokládejme klon v `~/dev/google-ads-app` (uprav cesty podle sebe).

### 1) Zkopíruj skill do své Claude Code složky se skilly

```bash
mkdir -p ~/.claude/skills
cp -R ~/dev/google-ads-app/skill/google-ads ~/.claude/skills/google-ads
```

### 2) Nastav skillu cestu k appce

Skill volá aplikaci přes placeholder `<GADS_APP_DIR>`. Nahraď ho **absolutní cestou** ke svému klonu:

```bash
# macOS — uprav cestu za = na svoji
APP_DIR="$HOME/dev/google-ads-app"
sed -i '' "s#<GADS_APP_DIR>#$APP_DIR#g" ~/.claude/skills/google-ads/SKILL.md
# na Linuxu: sed -i "s#<GADS_APP_DIR>#$APP_DIR#g" ~/.claude/skills/google-ads/SKILL.md
```

### 3) Ověř

Otevři Claude Code a napiš:

```
/google-ads
```

Zkus třeba `/google-ads create` a popiš svůj projekt. Claude se doptá na kontext, navrhne strukturu a **počká na tvoje schválení** — každý zápis jede nejdřív jako dry-run (validate-only) a nic se nezapíše bez `--confirm`.

## Co skill umí

- **research** — výzkum klíčových slov přes Keyword Planner
- **create** — struktura kampaně, RSA texty, assety, cílení, založení přes CLI (kampaň startuje PAUSED)
- **optimize** — `pulse` přehled, statistiky, úpravy bidů/negativ/rozpočtů
- **policy-check** — kontrola schválení inzerátů a policy problémů po vytvoření
- **negatives** — mining search terms → vylučující slova (vč. shared setů)
- **audiences** — remarketingová publika, napojení (observation/targeting), vyloučení

> Skill ti dává **mechaniku** (jak věci udělat nástrojem) a **pravidla** (co Google povoluje, jak psát inzeráty, bezpečnostní zábradlí). **Strategii průběžné optimalizace** — kdy co měnit, jaké KPI sledovat, jak reportovat — si nastav podle svých cílů a účtů. To je ta zajímavá část, kterou se učíš v kurzu. 🙂

## Doplň si skill o své vlastní know-how (doporučeno!)

Skill je **schválně univerzální**. Největší hodnotu z něj dostaneš, když si ho přizpůsobíš:

1. **Přidej vlastní referenční dokument.** Do `~/.claude/skills/google-ads/` vytvoř např. `moje-strategie.md`: tvoje postupy a prahy, cílové KPI/CPA/PNO, tón inzerátů značky, osvědčená negativa, sezónnost.
2. **Odkaž na něj ze `SKILL.md`** v sekci *Load Reference Documents*:
   ```
   - `moje-strategie.md` — moje postupy a firemní strategie (VŽDY přečíst)
   ```
3. **Klidně si uprav i scénáře** — reporting, deník, schvalovací proces.

## Aktualizace skillu

Když stáhneš novější verzi repa, zopakuj krok 1 (přepíše starou verzi) a krok 2 (znovu nastav cestu).
