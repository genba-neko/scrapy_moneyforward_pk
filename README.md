# scrapy_moneyforward

MoneyForward クローラ (Scrapy + Playwright)。旧 `scrapy_moneyforward` の
Splash/Lua 依存を撤廃し、`scrapy-playwright` ベースへ完全移行したもの。

参考構造: [`scrapy_smbcnikko_pk`](../scrapy_smbcnikko_pk)。

旧 `scrapy_moneyforward` からの対応表は [`docs/migration_mapping.md`](docs/migration_mapping.md) 参照。

## 前提

- Python 3.10+
- Playwright 同梱の Chromium
- (任意) Slack Incoming Webhook

## セットアップ

```powershell
# 1. 仮想環境
python -m venv .venv-win

# 2. 依存インストール
.venv-win\Scripts\pip install -r requirements.txt

# 3. Playwright ブラウザ取得
.venv-win\Scripts\python -m playwright install chromium

# 4. 環境変数
copy .env.example .env
# .env を編集 (SITE_LOGIN_USER / SITE_LOGIN_PASS 等)
```

## 実行

### crawl_runner (推奨)

`config/accounts.yaml` から site × account を読み、3 spider 種別を順次クロール:

```bash
cd src
python -m moneyforward.crawl_runner                   # 全 site × 全 account × 全種別
python -m moneyforward.crawl_runner --type transaction # 全 site × 全 account, transaction のみ
python -m moneyforward.crawl_runner --site xmf_ssnb    # xmf_ssnb のみ
python -m moneyforward.crawl_runner --list             # 起動予定一覧 (実行しない)
```

`config/accounts.example.yaml` をコピーして `config/accounts.yaml` を作成 (gitignore 対象)。

### job_runner (互換)

```powershell
# Windows
job_runner.bat transaction
```

```bash
# WSL / Linux
./job_runner.sh transaction      # transaction 種別のみ
./job_runner.sh all              # 全種別
```

内部で `crawl_runner --type X` を呼ぶ。

### 単発 scrapy crawl

```bash
cd src
python -m scrapy crawl transaction -a site=mf
python -m scrapy crawl account -a site=xmf_ssnb
python -m scrapy crawl asset_allocation -a site=xmf_jabank
```

env `SITE_LOGIN_USER` / `SITE_LOGIN_PASS` をフォールバックとして使用。

ヘッドレス無効:

```bash
MONEYFORWARD_HEADLESS=false ./job_runner.sh transaction
```

## スパイダー

3 個の汎用 spider クラスが site を引数 (`-a site=<variant>`) で受け取る。

| name | 対象 | 出力 Item |
|-----|-----|----------|
| `transaction` | `/cf` (月別) | `MoneyforwardTransactionItem` |
| `asset_allocation` | `/bs/portfolio` | `MoneyforwardAssetAllocationItem` |
| `account` | `/accounts` + 更新ボタン | `MoneyforwardAccountItem` |

### Site (variant) 一覧

site 設定は [`spiders/variants/registry.py`](src/moneyforward/spiders/variants/registry.py) の `VARIANTS` dict で管理:

| site | base URL | 由来 |
|---|---|---|
| `mf` | `https://moneyforward.com/` | 本体 |
| `xmf` | `https://x.moneyforward.com/` | 一般 partner portal |
| `xmf_ssnb` | `https://ssnb.x.moneyforward.com/` | 住信SBIネット銀行 |
| `xmf_mizuho` | `https://mizuho.x.moneyforward.com/` | みずほ銀行 |
| `xmf_jabank` | `https://jabank.x.moneyforward.com/` | JAバンク |
| `xmf_smtb` | `https://smtb.x.moneyforward.com/` | 三井住友信託銀行 |
| `xmf_linkx` | `https://linkx.x.moneyforward.com/` | linkx家計簿 |
| `xmf_okashin` | `https://okashin.x.moneyforward.com/` | 岡崎信用金庫 |
| `xmf_shiga` | `https://shiga.x.moneyforward.com/` | 滋賀銀行 |
| `xmf_shiz` | `https://shiz.x.moneyforward.com/` | 静岡銀行 |

### スパイダー引数

```bash
# site 切替 + 取得月数を引数で上書き (default: SITE_PAST_MONTHS=12)
cd src && python -m scrapy crawl transaction -a site=xmf_ssnb -a past_months=3
```

## 集計レポート (`reports/` パッケージ)

旧 PJ の `get_balances_report.py` / `get_asset_allocation_report.py` /
`get_balances_csv.py` を JSONL 入力ベースに移植したもの。

```powershell
# JSONL 出力から月次収支サマリを Slack 形式で生成
..\.venv-win\Scripts\python -m moneyforward.reports balances 2026 4

# 1 年分の CSV を標準出力に書く
..\.venv-win\Scripts\python -m moneyforward.reports balances-csv 2026

# 資産配分のサマリ
..\.venv-win\Scripts\python -m moneyforward.reports asset-allocation 2026 4 25
```

純関数 `aggregate_balances` / `aggregate_assets` / `report_message` /
`report_csv` を `tests/test_reports_*_unit.py` で固定。

## 証券 CSV → 配当データ (`seccsv/` パッケージ)

旧 PJ `seccsv_download/seccsv_to_incomes.py` を移植。SBI / 楽天証券 /
マネックス証券 / 松井証券 の 4 形式 CSV を判別し、配当・分配金を
`MoneyforwardTransactionItem` 互換形に正規化する。

```powershell
..\.venv-win\Scripts\python -m moneyforward.seccsv path/to/SaveFile.csv
```

`tests/fixtures/seccsv/*_anonymized.csv` で 4 broker 全パスをカバーする
ユニットテストを `tests/test_seccsv_*_unit.py` に配置している。

## 出力

`JsonArrayOutputPipeline` が **3 ファイル集約** で JSON 配列を書き出す
(元 PJ の出力 contract と同じ)。

- 出力先: `OUTPUT_DIR` (default: `runtime/output/`、プロジェクトルート配下のみ許可)
- ファイル名: `moneyforward_{spider_type}.json` の 3 ファイル固定
  - `moneyforward_transaction.json`
  - `moneyforward_account.json`
  - `moneyforward_asset_allocation.json`
- 形式: 単一の JSON 配列 (`json.load()` 可能)
- crawl_runner が起動前に 3 ファイルを `[` で初期化、終了時に `]` で閉じる
- アイテムレベルのサイト識別は `asset_item_key = "{site}_{spider_type}-{user}-{type}"` 等の key 経由

## ディレクトリ構造

```
scrapy_moneyforward/
├── src/
│   ├── scrapy.cfg
│   └── moneyforward/
│       ├── settings.py                 # Playwright wiring, .env 読込
│       ├── items.py
│       ├── pipelines.py                # JsonOutputPipeline (JSON Lines)
│       ├── middlewares/
│       │   └── playwright_session.py   # 再認証
│       ├── spiders/
│       │   ├── base/moneyforward_base.py   # ログイン共通基底
│       │   ├── _parsers.py             # HTML → Item (テスト容易化のため分離)
│       │   ├── transaction.py
│       │   ├── asset_allocation.py
│       │   └── account.py
│       └── utils/
│           ├── playwright_utils.py
│           ├── logging_config.py
│           ├── session_utils.py
│           └── slack_notifier.py
├── tests/                              # pytest (81 tests, coverage 86%)
├── plan/
├── .env.example
├── requirements.txt
├── pyproject.toml
├── job_runner.{bat,sh}
└── README.md
```

## テスト

```powershell
.venv-win\Scripts\pytest
```

パーサ・パイプライン・ミドルウェア・設定を単体テスト。Playwright 実通信は
含まない (手動 / E2E は別途)。

## 主要設計判断

- `PLAYWRIGHT_CONTEXTS = {}` 空 — 最初の `Request` が `storage_state` を
  `playwright_context_kwargs` で注入する余地を残すため (smbcnikko_pk と同一方針)。
- `_parsers.py` でパースを純関数化 → HTML fixture だけでテスト可能。
- 出力は JSON Lines 単一バックエンド (`JsonOutputPipeline`)。AWS 不要。
- 2FA は非対応 (旧プロジェクトも未対応)。必要なら `MoneyforwardBase.login_flow`
  をサブクラスで上書き。
- パートナーポータル (`*.x.moneyforward.com`) は `XMoneyforwardLoginMixin`
  で拡張可能。v1 では具象スパイダー未提供。

## 運用

### 定期実行 (GitHub Actions)

`.github/workflows/scrapy-nightly.yml` が毎日 18:00 UTC (JST 03:00) に
`workflow_dispatch` 互換の smoke ジョブを起動する。submodule に依存しない
ため、private workbench submodule の取得失敗で job が止まらない。
本番のクロールは OS のスケジューラから `job_runner.bat` / `job_runner.sh`
を起動する想定で、CI は `scrapy list` での import 健全性確認のみ。

### Slack 通知

`SLACK_INCOMING_WEBHOOK_URL` を設定すると `SlackNotifierExtension` が
`spider_closed` シグナルに購読し、終了理由・取得件数・経過秒を 1 行の
テキストで投稿する。未設定時は extension が `NotConfigured` を投げて
スキップされ、no-op で動作する。

### 出力ローテーション

`JsonOutputPipeline.open_spider` 起動時に `OUTPUT_RETENTION_DAYS`
(default 14、env で上書き) を超過した同一スパイダーの jsonl ファイルを
削除する。他スパイダーのファイルは保持される。`0` を指定すると
ローテーション無効。

### セッション切れ時の再ログイン

`PlaywrightSessionMiddleware` は `/sign_in` 等のログイン URL/タイトルを
検出すると `meta["moneyforward_force_login"]=True` を立て、対象 Request
を `MoneyforwardBase.handle_force_login` に渡す。これが
`_build_login_request(follow_up=...)` を経由して新しいログイン試行を
Request 化し、ログイン成功後に元の Request を再生する。再認証が
発生したら stats counter `<spider>/login/forced` が 1 加算される。

### アカウント切替 (`SITE_LOGIN_ALT_USER`)

`SITE_LOGIN_ALT_USER` / `SITE_LOGIN_ALT_PASS` を `.env` に両方設定すると、
`PlaywrightSessionMiddleware` が再試行を発火させた際 (login_retry_times >= 1)
に `MoneyforwardBase._resolve_credentials` が代替アカウントへ自動切替する。
`alt_user_used` stats counter (`<spider>/login/alt_user_used`) が 1 加算される。

- 一次ログイン (`login_attempt=0`) は常に `SITE_LOGIN_USER` / `SITE_LOGIN_PASS`
- 再ログイン (`login_attempt>=1`) は alt が両方設定されているときのみ alt
- alt が片方しか設定されていない場合は primary 維持 (regression なし)
- 認証情報はログに出力されない (詳細は「セキュリティ」節)

## セキュリティ

- `paths.resolve_output_dir` は `is_relative_to(PROJECT_ROOT)` で
  PROJECT_ROOT の外を指す `OUTPUT_DIR` を `ValueError` で拒否する。
  シンボリックリンクや `..` を含むパスは `Path.resolve` で吸収。
- `paths.sanitize_spider_name` は `[A-Za-z0-9_-]` 以外を `_` に置換し、
  `..` や `/` を含むスパイダー名でも安全な出力ファイル名を生成する。
- 認証情報 (`SITE_LOGIN_USER` / `SITE_LOGIN_PASS` / `SITE_LOGIN_ALT_USER` /
  `SITE_LOGIN_ALT_PASS`) は `.env` から `load_dotenv` で読み込まれ、
  コミット禁止 (`.gitignore` 推奨)。 `pytest` 実行時はモジュール import 時の
  `load_dotenv` をスキップしてシェル env が漏れないようにしている。
- **ログ redaction**: `utils/log_filter.SensitiveDataFilter` が `setup_common_logging`
  で root / scrapy / project logger に attach され、以下を `[REDACTED]` に置換:
  - URL クエリの `auth=` / `token=` / `access_token=` / `api_key=` 値
  - `Cookie:` / `Set-Cookie:` ヘッダ
  - `Authorization:` ヘッダ
  - `password=` / `passwd=` / `pwd=` の kv 値
  これにより `logger.exception` で URL / cookie / auth が混入しても
  ログファイルに生では出ない。フィルタは idempotent で重複 attach されない。
- **静的リソース blocklist**: `playwright_utils._BLOCK_RESOURCE_TYPES` は
  `image` / `font` / `media` のみ block (CSS は layout-critical のため通す)。
  分析・広告系 URL (`google-analytics`, `googletagmanager`, `hotjar`,
  `doubleclick`, `facebook.com/tr`) は URL pattern allow-list で別途 block。

### 出力ファイル ローテーションの fail-safe

`JsonOutputPipeline._prune_stale` は同一 spider の古い jsonl 削除を試みる。
ファイルがレース等で消えた場合 (`FileNotFoundError`) は黙って継続し、
それ以外の `OSError` は警告ログのみで pipeline 自体は止めない。

## 改善余地

- パートナーポータル具象スパイダー (xmf_ssnb, xmf_mizuho ほか) の追加
- 2FA (メール/SMS/Authenticator) 対応
- Playwright `storage_state` 永続化によるログインスキップ
- HTML inspector middleware (デバッグ保存) の移植
- 実通信を伴う integration テスト
