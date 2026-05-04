# scrapy_moneyforward_pk

MoneyForward クローラ (Scrapy + scrapy-playwright)。複数サイト × 複数アカウントに対応。

内部構造の詳細は [ARCHITECTURE.md](ARCHITECTURE.md) 参照。

## 前提

- Python 3.10+
- Playwright 同梱の Chromium

## セットアップ

```powershell
python -m venv .venv-win
.venv-win\Scripts\pip install -r requirements.txt
.venv-win\Scripts\python -m playwright install chromium
copy .env.example .env   # .env を編集
```

## 実行

### crawl_runner (推奨)

`config/accounts.yaml` からサイト × アカウントを読み込み、3 種別を順次クロール:

```bash
cd src
python -m moneyforward.crawl_runner                    # 全サイト × 全アカウント × 全種別
python -m moneyforward.crawl_runner --type transaction # transaction のみ
python -m moneyforward.crawl_runner --site xmf_ssnb    # xmf_ssnb のみ
python -m moneyforward.crawl_runner --list             # 起動予定一覧（実行しない）
```

`config/accounts.example.yaml` をコピーして `config/accounts.yaml` を作成 (gitignore 対象)。

### job_runner (互換)

```powershell
job_runner.bat transaction
```

```bash
./job_runner.sh all        # 全種別
./job_runner.sh transaction
```

内部で `crawl_runner --type X` を呼ぶ。

### 単発 scrapy crawl

```bash
cd src
python -m scrapy crawl transaction -a site=mf
python -m scrapy crawl account -a site=xmf_ssnb
python -m scrapy crawl asset_allocation -a site=xmf_jabank
```

`SITE_LOGIN_USER` / `SITE_LOGIN_PASS` を env フォールバックとして使用。
複数サイト・複数アカウント運用は crawl_runner 経由が必須。

ヘッドレス無効:

```bash
MONEYFORWARD_HEADLESS=false ./job_runner.sh transaction
```

## スパイダー

3 個の汎用 spider が site を引数で受け取る:

| Spider | 対象 | 出力 Item |
|---|---|---|
| `transaction` | `/cf` 月別取引 | `MoneyforwardTransactionItem` |
| `asset_allocation` | `/bs/portfolio` | `MoneyforwardAssetAllocationItem` |
| `account` | `/accounts` + 更新 | `MoneyforwardAccountItem` |

### Site (variant) 一覧

`spiders/variants/registry.py` の `VARIANTS` dict で管理:

| site | base URL |
|---|---|
| `mf` | `https://moneyforward.com/` |
| `xmf` | `https://x.moneyforward.com/` |
| `xmf_ssnb` | `https://ssnb.x.moneyforward.com/` |
| `xmf_mizuho` | `https://mizuho.x.moneyforward.com/` |
| `xmf_jabank` | `https://jabank.x.moneyforward.com/` |
| `xmf_smtb` | `https://smtb.x.moneyforward.com/` |
| `xmf_linkx` | `https://linkx.x.moneyforward.com/` |
| `xmf_okashin` | `https://okashin.x.moneyforward.com/` |
| `xmf_shiga` | `https://shiga.x.moneyforward.com/` |
| `xmf_shiz` | `https://shiz.x.moneyforward.com/` |

## 集計レポート (`reports/` パッケージ)

```powershell
# 月次収支サマリ (Slack 形式)
..\.venv-win\Scripts\python -m moneyforward.reports balances 2026 4

# 1 年分 CSV を標準出力
..\.venv-win\Scripts\python -m moneyforward.reports balances-csv 2026

# 資産配分サマリ
..\.venv-win\Scripts\python -m moneyforward.reports asset-allocation 2026 4 25
```

## 証券 CSV → 配当データ (`seccsv/` パッケージ)

SBI / 楽天 / マネックス / 松井証券の 4 形式 CSV を判別し、配当・分配金を
`MoneyforwardTransactionItem` 互換形式に正規化する。

```powershell
..\.venv-win\Scripts\python -m moneyforward.seccsv path/to/SaveFile.csv
```

## 出力

`JsonArrayOutputPipeline` が 3 ファイル集約で JSON 配列を書き出す:

```
runtime/output/
├── moneyforward_transaction.json
├── moneyforward_account.json
└── moneyforward_asset_allocation.json
```

- 形式: `json.load()` 可能な単一 JSON 配列 (pretty-print, indent=2)
- crawl_runner が起動前に `[` で初期化、終了時に `\n]` で閉じる
- `OUTPUT_DIR` env で出力先変更可 (PROJECT_ROOT 配下のみ許可)

## ディレクトリ構造

```
scrapy_moneyforward_pk/
├── src/moneyforward/       # メインパッケージ (詳細は ARCHITECTURE.md)
│   ├── settings.py
│   ├── items.py
│   ├── pipelines.py
│   ├── crawl_runner.py
│   ├── _runner_core.py
│   ├── auth/
│   ├── extensions/
│   ├── middlewares/
│   ├── reports/
│   ├── seccsv/
│   ├── secrets/
│   ├── spiders/
│   └── utils/
├── tests/                  # pytest (296 tests, coverage 84%)
├── tools/
│   ├── passkey/
│   └── secrets/            # Bitwarden admin CLI
├── config/
│   └── accounts.example.yaml
├── data/                   # アーカイブ・バックアップ (gitignore)
├── runtime/                # クロール結果・ログ・inspect (gitignore)
├── plan/                   # 設計プラン・ループ状態
├── .env.example
├── requirements.txt
├── pyproject.toml
└── job_runner.{bat,sh}
```

## テスト

```powershell
.venv-win\Scripts\pytest tests/ -v
.venv-win\Scripts\pytest tests/ --cov=src/moneyforward --cov-report=term-missing
```

パーサ・パイプライン・ミドルウェア・設定を単体テスト。Playwright 実通信は含まない。

## 運用

### 定期実行 (GitHub Actions)

`.github/workflows/scrapy-nightly.yml` が毎日 18:00 UTC (JST 03:00) に
`scrapy list` による import 健全性確認のみ実行。本番クロールは OS スケジューラ
から `job_runner.bat` / `job_runner.sh` 起動。

### Slack 通知

`SLACK_INCOMING_WEBHOOK_URL` を設定すると `SlackNotifierExtension` が
`spider_closed` シグナルに応答し、終了理由・取得件数・経過時間を投稿する。
未設定時は `NotConfigured` で no-op。

### セッション切れ時の再ログイン

`PlaywrightSessionMiddleware` が `/sign_in` リダイレクトを検出すると
`moneyforward_force_login=True` を立て再ログインを試みる。
再試行回数は `MONEYFORWARD_LOGIN_MAX_RETRY` (default: 2) で制御する。

### セキュリティ

- `paths.resolve_output_dir`: `OUTPUT_DIR` が PROJECT_ROOT 外を指す場合 `ValueError`
- `SensitiveDataFilter`: `auth=` / `token=` / `Cookie:` / `Authorization:` / `password=` をログ上で `[REDACTED]` に置換
- 静的リソース blocklist: `image` / `font` / `media` + 広告・分析系 URL をブロック
