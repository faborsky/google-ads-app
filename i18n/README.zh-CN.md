# Google Ads App

[🇬🇧 English](../README.md) · [🇨🇿 Čeština](../README.cs.md) · [🇪🇸 Español](README.es.md) · [🇧🇷 Português](README.pt-BR.md) · [🇩🇪 Deutsch](README.de.md) · [🇫🇷 Français](README.fr.md) · **🇨🇳 简体中文** · [🇯🇵 日本語](README.ja.md) · [🇸🇪 Svenska](README.sv.md) · [🇳🇴 Norsk](README.nb.md) · [🇩🇰 Dansk](README.da.md)

一个通过官方 [Google Ads API](https://developers.google.com/google-ads/api)（v25）管理 **Google Ads 搜索广告系列**的命令行工具。适合想在终端里管理广告系列、或把它交给 Claude Code 处理，而不想在 Google Ads 网页界面里来回点击的营销人员和创业者。

它覆盖搜索广告系列的完整生命周期：广告系列、广告组、RSA 广告、关键词和否定关键词、附加资源、受众、定位、预算、智能出价、转化、Google 建议、实验和 GAQL 报告。每次修改都先以试运行（dry-run）方式执行，应用还会自动监控 API 的每日配额。

作者：[Jindřich Fáborský](https://www.faborsky.com)

## 功能

- 85 个搜索广告系列命令，从 `campaign-create` 到 `experiment-promote`。
- `pulse`：用 5 次操作生成账户概览（汇总、变化、政策问题、警告）。
- 默认安全：每次变更都是 `validate_only` 试运行，只有加上 `--confirm` 才会写入。新广告系列以 PAUSED 状态启动。
- 配额保护（24 小时滑动窗口）和带退避的重试，避免误耗尽每日上限。
- `--json` 输出便于脚本和智能体使用，并附带一个 Claude Code 技能（`/google-ads`）。

## 快速开始

```bash
git clone https://github.com/faborsky/google-ads-app.git && cd google-ads-app
```

```bash
./setup.sh                # venv + dependencies + .env from the template (chmod 600)
# → fill in the credentials in .env (see Authentication)
./run.sh auth             # one-off: OAuth in the browser → the refresh token is written into .env
./run.sh accounts         # first live read = proof that everything works
```

完整文档（API 凭据、访问级别、全部命令、示例）为英文：**[README.md](../README.md)**。

## 许可证

MIT · [LICENSE](../LICENSE)

## 作者

[Jindřich Fáborský](https://www.faborsky.com)，来自布拉格的营销人和讲师，教营销人员用 AI 自己做工具。
