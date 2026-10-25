# Google Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · **🇧🇷 Português** · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

CLI para gerenciar **campanhas de pesquisa no Google Ads** pela [Google Ads API](https://developers.google.com/google-ads/api) oficial (v25). Para profissionais de marketing e fundadores que querem tocar as campanhas pelo terminal, ou entregá-las ao Claude Code, em vez de clicar na interface web do Google Ads.

Cobre todo o ciclo de vida de uma campanha de pesquisa: campanhas, grupos de anúncios, anúncios RSA, palavras-chave e negativas, assets, públicos, segmentação, orçamentos, Smart Bidding, conversões, recomendações do Google, experimentos e relatórios GAQL. Toda alteração é primeiro uma simulação (dry-run), e o app controla sozinho a cota diária da API.

Autor: [Jindřich Fáborský](https://www.faborsky.com)

## O que ele faz

- 85 comandos para campanhas de pesquisa, de `campaign-create` a `experiment-promote`.
- `pulse`: visão geral da conta em 5 operações (totais, variações, problemas de política, alertas).
- Seguro por padrão: toda mutação é um dry-run `validate_only`; só `--confirm` grava. Campanhas novas começam em PAUSED.
- Controle de cota (janela móvel de 24 h) e novas tentativas com back-off, para você não estourar o limite diário sem querer.
- Saída `--json` para scripts e agentes, além de um skill incluído para o Claude Code (`/google-ads`).

## Início rápido

```bash
git clone https://github.com/faborsky/google-ads-app.git && cd google-ads-app
```

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

A documentação completa (credenciais da API, níveis de acesso, todos os comandos, exemplos) está em inglês: **[README.md](../README.md)**.

## Licença

MIT · [LICENSE](../LICENSE)

## Autor

[Jindřich Fáborský](https://www.faborsky.com), profissional de marketing e educador de Praga. Ensino profissionais de marketing a criar suas próprias ferramentas com IA.
