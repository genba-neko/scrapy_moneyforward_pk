# Phase 5: 3 具象スパイダー + パーサ

実施日時: 2026-04-25 05:05 JST
所要: 約10分
コミット: `535328c` (合算)

## 目的
元 `scrapy_moneyforward` の 3 spider 機能を移植。HTML→Item パースを純関数化
してテスト容易化。

## 実施内容

### 1. `spiders/_parsers.py` (純関数, テスト対象)

#### `parse_transactions(response, year, month) -> Iterator[Item]`
元 `cache_flow_page` の selector 群を完全踏襲:
- `.transaction_list tr` ループ
- `td.date::attr(data-table-sortable-value)` から regex で year/month/day
- `.target-active` 有無で `is_active`
- `td.amount span::text` のカンマ + 円 除去で `amount_number`
- アカウント分岐 3 系統:
  - manual (`td.sub_account_id_hash span`)
  - auto (`td.note.calc`)
  - transfer (`td.calc:not([data-original-title=""])`)
- `lctg`/`mctg` 未分類フォールバック

#### `_parse_amount(view) -> int`
カンマ + 円 除去, 失敗 0。

#### `_extract_account_cells(row) -> tuple[str, str, str]`
manual/auto/transfer 3 分岐をまとめた純関数。

#### `parse_asset_allocation(response, spider_name, login_user, today) -> Iterator[Item]`
元 `portfolio_page` 踏襲:
- 最初の `<table>` の `<tr>` ループ
- `th a::text[0]` → `asset_name`
- `th a::attr(href)` の `#` 後 → `asset_type`
- `td::text[0]` の数値化 → `amount_value`
- `asset_item_key = f"{spider_name}-{login_user}-{asset_type}"`

#### `parse_accounts(response, today) -> tuple[list[Item], bool]`
元 `account_page` 踏襲:
- XPath `//th[contains(text(), "金融機関")]/parent::node()/parent::node()//tr`
- `td[0]` 結合 → `(本サイト)…` regex 削除
- `account_item_key = sha256(raw_name)`
- `td[3]` の `js-status-sentence-span-` (hidden 除外) 抽出
- `更新中` 検出 → `is_updating=True` 返却

### 2. `spiders/transaction.py` — `MfTransactionSpider`
- `name = "mf_transaction"`
- `-a past_months=N` または `SITE_PAST_MONTHS` (default 12)
- `after_login`: `dateutil.relativedelta` で過去 N ヶ月分 yield
- `parse_month(response, year, month)`:
  1. `.fc-button-selectMonth` クリック → 年クリック → 月クリック
  2. `networkidle` 待機
  3. `p.content()` → `parse_transactions` で yield
  4. `<spider>/records`, `<spider>/months_fetched` stats

### 3. `spiders/asset_allocation.py` — `MfAssetAllocationSpider`
- `name = "mf_asset_allocation"`
- `after_login`: `/bs/portfolio` を 1 リクエスト
- `parse_portfolio`: HTML 取得 → `parse_asset_allocation` で yield

### 4. `spiders/account.py` — `MfAccountSpider`
- `name = "mf_account"`
- `update_wait_seconds = 20`, `update_max_retry = 5`
- `after_login`: `_accounts_request(is_update=True, attempt=0)`
- `parse_accounts_page(response, is_update, attempt)`:
  1. `is_update=True` 初回のみ `_click_update_buttons` で全 `更新` ボタン押下
  2. `parse_accounts` で items + `is_updating` 取得
  3. `is_updating` かつ `attempt < max_retry` → `asyncio.sleep` → 自己再発行
  4. それ以外 → items yield + stats

#### `_click_update_buttons(page)`
- `td form input[value="更新"]` 全列挙 → 1 件ずつ click + 1s wait
- 失敗時は debug log で握りつぶし (一部失敗で全停止防止)

## 学び・判断
- パーサを spider クラスから完全分離 → fixture HTML 単体でテスト
- selector は元プロジェクト verbatim 維持 → DynamoDB record shape 変化なし
- `MfAccountSpider` の polling は元プロジェクトの `retry_count`/`retry_wait`
  をそのまま async/await へ移植
- `relativedelta` 必須 (`datetime.timedelta` では月跨ぎが正しく出ない)
