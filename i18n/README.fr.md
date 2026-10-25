# Google Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · **🇫🇷 Français** · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

CLI pour gérer des **campagnes Search sur Google Ads** via la [Google Ads API](https://developers.google.com/google-ads/api) officielle (v25). Pour les marketeurs et les fondateurs qui veulent piloter leurs campagnes depuis le terminal, ou les confier à Claude Code, plutôt que de cliquer dans l'interface web de Google Ads.

Il couvre tout le cycle de vie d'une campagne Search : campagnes, groupes d'annonces, annonces RSA, mots-clés et mots-clés négatifs, assets, audiences, ciblage, budgets, Smart Bidding, conversions, recommandations de Google, tests et rapports GAQL. Chaque modification passe d'abord par une simulation (dry-run), et l'app surveille elle-même le quota quotidien de l'API.

Auteur: [Jindřich Fáborský](https://www.faborsky.com)

## Ce qu'il fait

- 85 commandes pour les campagnes Search, de `campaign-create` à `experiment-promote`.
- `pulse` : vue d'ensemble du compte en 5 opérations (totaux, variations, problèmes de règles, alertes).
- Sûr par défaut : chaque mutation est un dry-run `validate_only`, seul `--confirm` écrit. Les nouvelles campagnes démarrent en PAUSED.
- Garde-fou de quota (fenêtre glissante de 24 h) et nouvelles tentatives avec back-off, pour ne pas épuiser la limite quotidienne par erreur.
- Sortie `--json` pour les scripts et les agents, plus un skill fourni pour Claude Code (`/google-ads`).

## Démarrage rapide

```bash
git clone https://github.com/faborsky/google-ads-app.git && cd google-ads-app
```

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

La documentation complète (identifiants de l'API, niveaux d'accès, toutes les commandes, exemples) est en anglais : **[README.md](../README.md)**.

## Licence

MIT · [LICENSE](../LICENSE)

## Auteur

[Jindřich Fáborský](https://www.faborsky.com), marketeur et formateur à Prague. J'apprends aux marketeurs à créer leurs propres outils avec l'IA.
