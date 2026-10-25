# Google Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · **🇳🇴 Norsk** · [🇩🇰 Dansk](README.da.md)

Et CLI for å administrere **søkekampanjer i Google Ads** via det offisielle [Google Ads API](https://developers.google.com/google-ads/api) (v25). For markedsførere og gründere som vil styre kampanjene fra terminalen, eller overlate dem til Claude Code, i stedet for å klikke seg rundt i nettgrensesnittet til Google Ads.

Det dekker hele livssyklusen til en søkekampanje: kampanjer, annonsegrupper, RSA-annonser, søkeord og negative søkeord, ressurser, målgrupper, målretting, budsjetter, Smart Bidding, konverteringer, Googles anbefalinger, eksperimenter og GAQL-rapporter. Hver endring kjøres først som en prøvekjøring (dry-run), og appen passer selv på den daglige API-kvoten.

Forfatter: [Jindřich Fáborský](https://www.faborsky.com)

## Hva det gjør

- 85 kommandoer for søkekampanjer, fra `campaign-create` til `experiment-promote`.
- `pulse`: kontooversikt på 5 operasjoner (totaler, endringer, retningslinjeproblemer, varsler).
- Trygt som standard: hver endring er en `validate_only`-prøvekjøring, først `--confirm` skriver. Nye kampanjer starter som PAUSED.
- Kvotevakt (glidende 24-timersvindu) og nye forsøk med back-off, så du ikke bruker opp dagsgrensen ved et uhell.
- `--json`-utdata for skript og agenter, pluss en medfølgende skill for Claude Code (`/google-ads`).

## Hurtigstart

```bash
git clone https://github.com/faborsky/google-ads-app.git && cd google-ads-app
```

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

Den fullstendige dokumentasjonen (API-legitimasjon, tilgangsnivåer, alle kommandoer, eksempler) er på engelsk: **[README.md](../README.md)**.

## Lisens

MIT · [LICENSE](../LICENSE)

## Forfatter

[Jindřich Fáborský](https://www.faborsky.com), markedsfører og underviser fra Praha. Jeg lærer markedsførere å bygge egne verktøy med AI.
