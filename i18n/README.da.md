# Google Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · **🇩🇰 Dansk**

Et CLI til at styre **søgekampagner i Google Ads** via det officielle [Google Ads API](https://developers.google.com/google-ads/api) (v25). Til marketingfolk og iværksættere, der vil køre kampagnerne fra terminalen, eller overlade dem til Claude Code, i stedet for at klikke rundt i Google Ads' webgrænseflade.

Det dækker hele livscyklussen for en søgekampagne: kampagner, annoncegrupper, RSA-annoncer, søgeord og negative søgeord, aktiver, målgrupper, målretning, budgetter, Smart Bidding, konverteringer, Googles anbefalinger, eksperimenter og GAQL-rapporter. Hver ændring kører først som en prøvekørsel (dry-run), og appen holder selv øje med den daglige API-kvote.

Forfatter: [Jindřich Fáborský](https://www.faborsky.com)

## Hvad det gør

- 85 kommandoer til søgekampagner, fra `campaign-create` til `experiment-promote`.
- `pulse`: kontooversigt på 5 operationer (totaler, ændringer, politikproblemer, advarsler).
- Sikkert som standard: hver ændring er en `validate_only`-prøvekørsel, først `--confirm` skriver. Nye kampagner starter som PAUSED.
- Kvotevagt (glidende 24-timersvindue) og genforsøg med back-off, så du ikke kommer til at bruge dagsgrænsen op.
- `--json`-output til scripts og agenter, plus en medfølgende skill til Claude Code (`/google-ads`).

## Hurtig start

```bash
git clone https://github.com/faborsky/google-ads-app.git && cd google-ads-app
```

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

Den fulde dokumentation (API-adgangsoplysninger, adgangsniveauer, alle kommandoer, eksempler) er på engelsk: **[README.md](../README.md)**.

## Licens

MIT · [LICENSE](../LICENSE)

## Forfatter

[Jindřich Fáborský](https://www.faborsky.com), marketingmand og underviser fra Prag. Jeg lærer marketingfolk at bygge deres egne værktøjer med AI.
