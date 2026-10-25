# Google Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · **🇩🇪 Deutsch** · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

CLI zur Verwaltung von **Google-Ads-Suchkampagnen** über die offizielle [Google Ads API](https://developers.google.com/google-ads/api) (v25). Für Marketer und Gründer, die ihre Kampagnen im Terminal steuern oder an Claude Code übergeben wollen, statt sich durch die Weboberfläche von Google Ads zu klicken.

Es deckt den ganzen Lebenszyklus einer Suchkampagne ab: Kampagnen, Anzeigengruppen, RSA-Anzeigen, Keywords und Negatives, Assets, Zielgruppen, Targeting, Budgets, Smart Bidding, Conversions, Google-Empfehlungen, Experimente und GAQL-Reports. Jede Änderung läuft zuerst als Probelauf (Dry-Run), und die App überwacht das tägliche API-Kontingent selbst.

Autor: [Jindřich Fáborský](https://www.faborsky.com)

## Was es kann

- 85 Befehle für Suchkampagnen, von `campaign-create` bis `experiment-promote`.
- `pulse`: Kontoübersicht in 5 Operationen (Summen, Veränderungen, Richtlinienprobleme, Warnungen).
- Standardmäßig sicher: Jede Änderung ist ein `validate_only`-Dry-Run, erst `--confirm` schreibt. Neue Kampagnen starten PAUSED.
- Kontingentwächter (gleitendes 24-h-Fenster) und Retry mit Back-off, damit du das Tageslimit nicht aus Versehen aufbrauchst.
- `--json`-Ausgabe für Skripte und Agenten, dazu ein mitgeliefertes Skill für Claude Code (`/google-ads`).

## Schnellstart

```bash
git clone https://github.com/faborsky/google-ads-app.git && cd google-ads-app
```

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

Die vollständige Dokumentation (API-Zugangsdaten, Zugriffsstufen, alle Befehle, Beispiele) gibt es auf Englisch: **[README.md](../README.md)**.

## Lizenz

MIT · [LICENSE](../LICENSE)

## Autor

[Jindřich Fáborský](https://www.faborsky.com), Marketer und Dozent aus Prag. Ich bringe Marketern bei, mit KI eigene Tools zu bauen.
