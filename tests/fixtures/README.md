# tests/fixtures/

Real-HTML captures from the legacy `scrapy_moneyforward` project, used as
regression anchors so iter-by-iter selector edits cannot silently regress on
authentic markup. Loaders live in `tests/conftest.py` (`fixture_html`).

| ファイル | 出典 (元 PJ パス) | URL | 取得日 (推定) | 抽出範囲 |
|---|---|---|---|---|
| `mf_transaction_legacy.html` | `scrapy_moneyforward/tests/fixtures/cf.html` 相当 | `https://moneyforward.com/cf` (月別) | 2019-11 (data-table-sortable-value 由来) | `<tbody>` 配下の `<tr class="js-cf-edit-container target-active transaction_list">` 3 行のみ。フォーム/script/banner 等は削除済み |
| `mf_asset_allocation_legacy.html` | `scrapy_moneyforward/tests/fixtures/portfolio.html` 相当 | `https://moneyforward.com/bs/portfolio` | 2025-01 ごろ | 1 番目の `<table class="table table-bordered">` のみ。サマリ/フッタ table は削除済み |
| `mf_accounts_legacy.html` | `scrapy_moneyforward/tests/fixtures/accounts.html` 相当 | `https://moneyforward.com/accounts` | 2025-01 ごろ | 9 行の登録金融機関テーブル。js-status-sentence-span / js-hidden-status-sentence-span を維持 |

## スクラブ方針

- メールアドレス・口座名義・残高など PII はマスクまたは一般化済み。
- `<script>` / `<link rel="stylesheet">` / `<svg>` / 大量バナー DOM は除去済み (パーサのターゲット外)。
- `data-original-title` / `data-table-sortable-value` などセレクタが見る属性は維持。

## 追加方針

新規 fixture を追加する場合は:

1. PII を必ずスクラブ (検索置換で確実に消す)
2. 上記表に行を追加 (出典・URL・取得日・抽出範囲)
3. `tests/test_parsers_legacy_fixtures_unit.py` 等に最低 1 件の assert を書く
4. `pytest tests/ -v` で全 pass を確認してからコミット
