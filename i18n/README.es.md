# Google Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · **🇪🇸 Español** · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

CLI para gestionar **campañas de búsqueda en Google Ads** a través de la [Google Ads API](https://developers.google.com/google-ads/api) oficial (v25). Para marketers y fundadores que quieren llevar sus campañas desde la terminal, o dejarlas en manos de Claude Code, en lugar de hacer clic en la interfaz web de Google Ads.

Cubre todo el ciclo de vida de una campaña de búsqueda: campañas, grupos de anuncios, anuncios RSA, palabras clave y negativas, assets, audiencias, segmentación, presupuestos, Smart Bidding, conversiones, recomendaciones de Google, experimentos e informes GAQL. Cada cambio es primero una simulación (dry-run) y la app vigila sola la cuota diaria de la API.

Autor: [Jindřich Fáborský](https://www.faborsky.com)

## Qué hace

- 85 comandos para campañas de búsqueda, desde `campaign-create` hasta `experiment-promote`.
- `pulse`: resumen de la cuenta en 5 operaciones (totales, variaciones, problemas de políticas, avisos).
- Seguro por defecto: cada mutación es un dry-run `validate_only`; solo `--confirm` escribe. Las campañas nuevas empiezan en PAUSED.
- Guardia de cuota (ventana móvil de 24 h) y reintentos con back-off, para no agotar el límite diario por error.
- Salida `--json` para scripts y agentes, más un skill incluido para Claude Code (`/google-ads`).

## Inicio rápido

```bash
git clone https://github.com/faborsky/google-ads-app.git && cd google-ads-app
```

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

La documentación completa (credenciales de la API, niveles de acceso, todos los comandos, ejemplos) está en inglés: **[README.md](../README.md)**.

## Licencia

MIT · [LICENSE](../LICENSE)

## Autor

[Jindřich Fáborský](https://www.faborsky.com), marketer y formador de Praga. Enseño a los marketers a crear sus propias herramientas con IA.
