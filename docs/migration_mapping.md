# Legacy → scrapy_moneyforward_pk 移植マッピング

旧 `scrapy_moneyforward` (Scrapy + Splash + Lua) から本リビルド
`scrapy_moneyforward_pk` (Scrapy + Playwright) への対応表。

実装場所 (旧) は `genba-neko/scrapy_moneyforward` リポジトリ、
新は本リポジトリ `src/moneyforward_pk/` 配下を指す。

## 全体方針

| 観点 | legacy | scrapy_moneyforward_pk |
|---|---|---|
| ブラウザ駆動 | Splash + Lua スクリプト | scrapy-playwright (Chromium 同梱) |
| Python 要件 | 3.8 系 | 3.10+ |
| データ出力 | DynamoDB (boto3) | JSON Lines (`runtime/output/`) |
| 実行基盤 | docker-compose + fluent-bit | GitHub Actions schedule (任意 docker) |
| 通知 | カスタム slack スクリプト | `SlackNotifierExtension` (Scrapy 標準フック) |
| ログ秘匿 | (なし) | `SensitiveDataFilter` |
| 認証 | 単一アカウント | 主 + 代替 (alt user) 切替 |

## ファイル/モジュール対応表

| # | legacy | scrapy_moneyforward_pk | 移植状況 |
|---|---|---|---|
| 1 | `splash/login.lua` (Lua) | `spiders/base/x_moneyforward_login_mixin.py` (`login_flow`) | ★ 移植 (Playwright async) |
| 2 | `splash/wait_render.lua` | `utils/playwright_utils.py` (`managed_page` ctx) | ★ 移植 |
| 3 | `pipelines.py::DynamoDBPipeline` | `pipelines.py::JsonOutputPipeline` | ☆ 仕様変更 (USER_DIRECTIVES) |
| 4 | `spiders/mf_transaction.py` | `spiders/transaction.py` | ★ 移植 (XPath / td.calc 対応) |
| 5 | `spiders/mf_asset_allocation.py` | `spiders/asset_allocation.py` | ★ 移植 (1番目 table 限定) |
| 6 | `spiders/mf_account.py` | `spiders/account.py` | ★ 移植 |
| 7 | `middlewares.py` (scaffold) | `middlewares/playwright_session.py` | ★ 拡張 (session 失効リトライ) |
| 8 | (なし) | `middlewares/html_inspector.py` | ◎ 新規 (debug 用 opt-in) |
| 9 | (なし) | `extensions/slack_notifier_extension.py` | ★ 移植 (Scrapy 標準形) |
| 10 | (なし) | `utils/log_filter.py` (`SensitiveDataFilter`) | ◎ 新規 (機密 redact) |
| 11 | (なし) | `utils/paths.py` | ◎ 新規 (output 安全境界) |
| 12 | `dynamodb/*` (boto3 helpers) | (撤去) | ☓ 撤去 (USER_DIRECTIVES) |
| 13 | `bg-docker-compose.yml` / `fluent-bit.conf` | (Out-of-scope) | ☓ 別 PJ 管轄 |
| 14 | `tables/` (DynamoDB ヘルパー) | (撤去) | ☓ JSON 出力で代替 (USER_DIRECTIVES) |
| 15 | `get_balances_report.py` | `reports/balances.py` (`aggregate_balances` / `report_message` / `report_csv`) | ★ 移植 (c3 iter1 T2) |
| 16 | `get_asset_allocation_report.py` | `reports/asset_allocation.py` (`aggregate_assets` / `report_message`) | ★ 移植 (c3 iter1 T2) |
| 17 | `get_balances_csv.py` | `reports/cli.py` (`python -m moneyforward_pk.reports`) | ★ 移植 (c3 iter1 T2) |
| 18 | `seccsv_download/seccsv_to_incomes.py` | `seccsv/converter.py` (`convert_csv` / `_parsers.py`) | ★ 移植 (c3 iter1 T3, 4 broker 対応) |
| 19 | `MfSpider` 多態継承 (1 ファイル 10 クラス) | `spiders/variants/registry.py::VARIANTS` (`VariantConfig` dataclass) | ★ 設計変更 (c3 iter1 T4 + iter2 T2/T4) |
| 20 | `xmf_ssnb` 系 3 spider | `spiders/xmf_ssnb_*.py` (3 ファイル × 4 行 subclass) | ★ 移植 (c3 iter2 T3) |
| 21 | 元 PJ 8 派生サイト (`xmf` / `xmf_mizuho` / `xmf_jabank` / `xmf_smtb` / `xmf_linkx` / `xmf_okashin` / `xmf_shiga` / `xmf_shiz`) | `spiders/xmf*.py` × 24 ファイル (登録のみ、selector 調査は実環境必須) | ★ 登録 (c3 iter2 T4) |
| 22 | `report_*.py` blog 出力 (note.com) | (Out-of-scope) | ☓ note.com SaaS 依存 (USER_DIRECTIVES) |

凡例: ★ 機能維持移植 / ☆ 仕様変更移植 / ◎ 新規追加 / ☓ 撤去 or OOS

## 環境変数 (主要)

| legacy | scrapy_moneyforward_pk | 備考 |
|---|---|---|
| `MF_USER` / `MF_PASS` | `SITE_LOGIN_USER` / `SITE_LOGIN_PASS` | リネーム |
| (なし) | `SITE_LOGIN_ALT_USER` / `SITE_LOGIN_ALT_PASS` | 新規 (HA 用) |
| `MF_PAST_MONTHS` | `SITE_PAST_MONTHS` | 同義リネーム |
| `DYNAMODB_TABLE_NAME` | (廃止) → `OUTPUT_DIR` / `OUTPUT_FILENAME_TEMPLATE` | 出力先変更 |
| (なし) | `OUTPUT_RETENTION_DAYS` | jsonl 自動 prune 閾値 |
| (なし) | `MONEYFORWARD_HEADLESS` | Playwright headless 切替 |
| (なし) | `MONEYFORWARD_LOGIN_MAX_RETRY` | session 失効再ログイン上限 |
| (なし) | `MONEYFORWARD_HTML_INSPECTOR` | debug 用 HTML dump |
| (なし) | `SLACK_INCOMING_WEBHOOK_URL` | Slack 通知 (空なら no-op) |
| (なし) | `LOG_FILE_ENABLED` / `LOG_FILE_PATH` | ファイルログ切替 |

## 実行コマンド

| 用途 | legacy | scrapy_moneyforward_pk |
|---|---|---|
| transaction 取得 (mf 本体) | `scrapy crawl mf` (transactions) | `scrapy crawl mf_transaction` |
| asset 取得 (mf 本体) | `scrapy crawl mf_asset_allocation` (legacy 名同一) | `scrapy crawl mf_asset_allocation` |
| account 取得 (mf 本体) | `scrapy crawl mf_account` | `scrapy crawl mf_account` |
| 派生サイト (例: 住信SBI) | `scrapy crawl xmf_ssnb` | `scrapy crawl xmf_ssnb_transaction` (他 24 派生スパイダー同様) |
| 集計レポート (CSV) | `python get_balances_csv.py 2024` | `python -m moneyforward_pk.reports balances 2024` |
| 配当 CSV 変換 | `python seccsv_to_incomes.py path.csv` | `python -m moneyforward_pk.seccsv path.csv` |
| バッチ実行 | `bg_job_runner.bat` (docker) | `job_runner.bat <name>` (素のホスト) |
| スケジュール | host cron / Windows タスク | `.github/workflows/scrapy-nightly.yml` |

## 廃止された依存

- `scrapy-splash` (Splash サービス連携)
- `boto3` (DynamoDB I/O)
- `fluent-bit` (ログ集約)
- `docker-compose.yml` / `bg-docker-compose.yml` (本 PJ 管轄外)

## 残課題 (Out-of-scope 維持)

下記は本キャンペーンで意図的に未移植。詳細は `plan/CURRENT_ITERATION.md` の
`out_of_scope` フィールド参照:

- 派生サイト 8 系統の HTML 構造調査 + selector 差分吸収 (`xmf*` 系、登録のみ済 / selector は実環境必須)
- 2FA 対応 (テスト戦略確立要)
- 高度 stealth fingerprint (canvas / WebGL)
- docker 運用基盤一式 (fluent-bit / bg-docker-compose)
- blog 投稿 (note.com SaaS 依存、USER_DIRECTIVES で OOS 確定)
- 元 PJ 完全比較表 (本ドキュメントは要点抜粋)
