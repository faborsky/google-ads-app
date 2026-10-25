# Google Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · [🇨🇳 简体中文](README.zh-CN.md) · **🇯🇵 日本語** · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

公式の [Google Ads API](https://developers.google.com/google-ads/api)（v25）で **Google 広告の検索キャンペーン**を管理する CLI です。Google 広告の管理画面をクリックして回る代わりに、ターミナルからキャンペーンを運用したい、あるいは Claude Code に任せたいマーケターや創業者向けです。

検索キャンペーンのライフサイクル全体をカバーします：キャンペーン、広告グループ、RSA 広告、キーワードと除外キーワード、アセット、オーディエンス、ターゲティング、予算、スマート自動入札、コンバージョン、Google の推奨事項、テスト、GAQL レポート。変更はすべてまずドライランで実行され、API の 1 日あたりの割り当てもアプリが自動で監視します。

作者：[Jindřich Fáborský](https://www.faborsky.com)

## できること

- 検索キャンペーン向けの 85 コマンド（`campaign-create` から `experiment-promote` まで）。
- `pulse`：5 回の操作でアカウント概要（合計、増減、ポリシー上の問題、警告）を表示。
- デフォルトで安全：変更はすべて `validate_only` のドライランで、`--confirm` を付けたときだけ書き込みます。新しいキャンペーンは PAUSED で開始。
- 割り当てガード（24 時間のスライディングウィンドウ）とバックオフ付きリトライで、うっかり 1 日の上限を使い切りません。
- スクリプトやエージェント向けの `--json` 出力と、Claude Code 用の同梱スキル（`/google-ads`）。

## クイックスタート

```bash
git clone https://github.com/faborsky/google-ads-app.git && cd google-ads-app
```

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

完全なドキュメント（API の認証情報、アクセスレベル、全コマンド、使用例）は英語です：**[README.md](../README.md)**

## ライセンス

MIT · [LICENSE](../LICENSE)

## 作者

[Jindřich Fáborský](https://www.faborsky.com)、プラハ在住のマーケター・講師。マーケターが AI で自分のツールを作れるよう教えています。
