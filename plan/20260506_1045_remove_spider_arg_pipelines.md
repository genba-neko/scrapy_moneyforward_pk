# fix: Pipeline の open_spider/close_spider/process_item から spider 引数除去 (#72)

## 背景

Scrapy 新バージョンで `open_spider()` / `close_spider()` / `process_item()` への `spider` 引数渡しが非推奨。将来バージョンで引数が渡されなくなり実行時エラー化する。

## 対象

- `src/moneyforward/pipelines/json_array.py` — `JsonArrayOutputPipeline`
- `src/moneyforward/pipelines/dynamodb.py` — `DynamoDbPipeline`

## 設計

### spider アクセス手段

`DynamoDbPipeline` は既に `from_crawler` で `self.crawler` 保持済み。
`JsonArrayOutputPipeline` は未保持 → `from_crawler` で `instance.crawler = crawler` 追加。

spider インスタンスは `self.crawler.spider` 経由でアクセス。

### シグネチャ変更

| メソッド | 変更前 | 変更後 |
|---|---|---|
| open_spider | `(self, spider)` | `(self)` |
| close_spider | `(self, spider)` | `(self)` |
| process_item | `(self, item, spider)` | `(self, item)` |

### ロガー変更

`spider.logger.*` → モジュールレベル `logger.*` に統一。

### JsonArrayOutputPipeline 追加変更

- `__init__`: `self.crawler = None`, `self._spider_name = ""` 追加
- `from_crawler`: `instance.crawler = crawler` 追加
- `open_spider`: `spider = self.crawler.spider` で取得, `self._spider_name = spider.name` 保存
- `close_spider`: `self.crawler.stats.set_value(...)` 経由でパス記録

## テスト更新

- `tests/test_pipelines_unit.py`: spider arg 除去、`pipeline.crawler.spider` セットアップ追加
- `tests/test_dynamodb_pipeline_unit.py`: spider arg 除去、`pipeline.crawler.spider` セットアップ追加、hook signature テスト更新

## ステータス

- [x] json_array.py 修正
- [x] dynamodb.py 修正
- [x] テスト更新
- [x] pytest パス確認 (40 passed)
- [ ] PR 作成
