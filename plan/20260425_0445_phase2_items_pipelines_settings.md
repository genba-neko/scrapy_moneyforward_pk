# Phase 2: Items / Pipelines / Settings

実施日時: 2026-04-25 04:45 JST
所要: 約7分
コミット: `535328c` (合算)

## 目的
Scrapy プロジェクトのコア層を実装。元 `scrapy_moneyforward` の Item 構造と
DynamoDB 互換性を維持しつつ Playwright 配線を確立。

## 実施内容

### 1. `src/moneyforward_pk/items.py`
3 Item クラス。元プロジェクトと完全同型 (DynamoDB partition/range key 互換)。
- `MoneyforwardTransactionItem` 16 fields, partition=`year_month`, range=`data_table_sortable_value`
- `MoneyforwardAssetAllocationItem` 10 fields, partition=`year_month_day`, range=`asset_item_key`
- `MoneyforwardAccountItem` 6 fields, partition=`year_month_day`, range=`account_item_key`

### 2. `src/moneyforward_pk/pipelines.py`
`DynamoDbPipeline` クラス。
- `from_crawler` で `DYNAMODB_TABLE_NAME` 必須化
- `open_spider` で boto3 lazy import → `Table` 取得
- `process_item` でバッファ蓄積, `DYNAMODB_BATCH_N` 達で `_flush`
- `_flush` で `batch_writer` 内 put_item ループ → `DYNAMODB_PUT_DELAY` sleep
- 失敗時 `DropItem` raise + log
- `close_spider` 残バッファ flush

### 3. `src/moneyforward_pk/settings.py`
smbcnikko_pk 流の bootstrap。
- `PROJECT_ROOT = Path(__file__).resolve().parents[2]`
- `RUNTIME_DIR = PROJECT_ROOT / "runtime"`
- `if "pytest" not in sys.modules: load_dotenv(...)`
- `_resolve_project_path()` ヘルパ
- Playwright 配線:
  - `DOWNLOAD_HANDLERS` http/https → `scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler`
  - `TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"`
  - `PLAYWRIGHT_BROWSER_TYPE = "chromium"`
  - `PLAYWRIGHT_LAUNCH_OPTIONS` headless 環境変数制御
  - **`PLAYWRIGHT_CONTEXTS = {}` 意図的に空** (storage_state 注入余地)
- `DOWNLOADER_MIDDLEWARES`: PlaywrightSessionMiddleware @600
- `ITEM_PIPELINES`: DynamoDbPipeline @300, ただし `DYNAMODB_TABLE_NAME` 空なら自動無効
- 環境変数公開: SITE_LOGIN_*, SITE_PAST_MONTHS, DYNAMODB_*, SLACK_*, LOG_*
- `RETRY_HTTP_CODES` に 400/408/429 追加 (元踏襲)

### 4. `src/moneyforward_pk/spiders/__init__.py`
空ファイル (パッケージ化のみ)。

## 学び・判断
- `DYNAMODB_TABLE_NAME` 空時の自動 pipeline 無効化により dev/CI で AWS 不要に
- `PLAYWRIGHT_CONTEXTS = {}` をコメント付きで強調 (default 注入で storage_state が消える既知問題)
- Item 構造を完全互換にしたため既存 DynamoDB テーブルそのまま使える
