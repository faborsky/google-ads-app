# Google Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · **🇸🇪 Svenska** · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

Ett CLI för att hantera **sökkampanjer i Google Ads** via det officiella [Google Ads API](https://developers.google.com/google-ads/api) (v25). För marknadsförare och grundare som vill sköta kampanjerna från terminalen, eller lämna över dem till Claude Code, i stället för att klicka runt i Google Ads webbgränssnitt.

Det täcker hela livscykeln för en sökkampanj: kampanjer, annonsgrupper, RSA-annonser, sökord och negativa sökord, tillgångar, målgrupper, inriktning, budgetar, Smart Bidding, konverteringar, Googles rekommendationer, experiment och GAQL-rapporter. Varje ändring körs först som en provkörning (dry-run), och appen håller själv koll på den dagliga API-kvoten.

Författare: [Jindřich Fáborský](https://www.faborsky.com)

## Vad det gör

- 85 kommandon för sökkampanjer, från `campaign-create` till `experiment-promote`.
- `pulse`: kontoöversikt på 5 operationer (totaler, förändringar, policyproblem, varningar).
- Säkert som standard: varje ändring är en `validate_only`-provkörning, först `--confirm` skriver. Nya kampanjer startar som PAUSED.
- Kvotvakt (glidande 24-timmarsfönster) och omförsök med back-off, så att du inte råkar förbruka dagsgränsen.
- `--json`-utdata för skript och agenter, plus en medföljande skill för Claude Code (`/google-ads`).

## Snabbstart

```bash
git clone https://github.com/faborsky/google-ads-app.git && cd google-ads-app
```

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

Den fullständiga dokumentationen (API-uppgifter, åtkomstnivåer, alla kommandon, exempel) finns på engelska: **[README.md](../README.md)**.

## Licens

MIT · [LICENSE](../LICENSE)

## Författare

[Jindřich Fáborský](https://www.faborsky.com), marknadsförare och utbildare från Prag. Jag lär marknadsförare att bygga egna verktyg med AI.
