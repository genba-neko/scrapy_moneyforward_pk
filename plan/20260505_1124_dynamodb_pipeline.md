# #67 DynamoDB パイプライン追加（JSON 併用）

作成日: 2026-05-05

## 概要

JSON 出力を維持したまま DynamoDB 書き込みパイプラインを追加する。
全テーブル名未設定時は no-op。既存動作に影響なし。

## 元PJとの互換要件

元 `scrapy_moneyforward` は spider_type ごとに**別テーブル**を使用（PK 設計が異なるため1テーブル混在不可）:

| spider_type     | HASH key        | RANGE key                    |
|-----------------|-----------------|------------------------------|
| transaction     | `year_month`    | `data_table_sortable_value`  |
| asset_allocation| `year_month_day`| `asset_item_key`             |
| account         | `year_month_day`| `account_item_key`           |

## 設計

### ファイル構成変更

```
src/moneyforward/
  pipelines.py              → 削除（パッケージ化）
  pipelines/
    __init__.py             # 新規: JsonArrayOutputPipeline + DynamoDbPipeline re-export
    json_array.py           # 新規: pipelines.py の内容をそのまま移動
    dynamodb.py             # 新規: DynamoDbPipeline + resolve_dynamodb_resource + _get_secret
```

`__init__.py` で両クラスを re-export → settings.py の短縮パス参照・既存インポートとも変更不要

### 環境変数（.env）

```
# DynamoDB テーブル名（spider_type ごとに個別設定）
DYNAMODB_TABLE_NAME_TRANSACTION=      # 未設定=スキップ
DYNAMODB_TABLE_NAME_ASSET_ALLOCATION= # 未設定=スキップ
DYNAMODB_TABLE_NAME_ACCOUNT=          # 未設定=スキップ

# AWS 認証（resolver 経由: env mode = os.environ / bitwarden mode = BWS キャッシュ）
# [Bitwarden 対象] BWS キー: MONEYFORWARD_AWS_ACCESS_KEY_ID / MONEYFORWARD_AWS_SECRET_ACCESS_KEY
# 未設定時は SecretNotFound → None → boto3 デフォルト chain (IAM ロール / ~/.aws/config)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=ap-northeast-1  # 機密でないため os.environ 直読み（resolver 非経由）

# バッチ制御
DYNAMODB_PUT_DELAY=3
DYNAMODB_BATCH_N=10
```

### DynamoDbPipeline 仕様（smbcnikko_pk パターン準拠）

```
from_crawler:
  - 3テーブル名を settings から .strip() 取得
  - 全て空 → raise NotConfigured（Scrapy が自動無効化、例外なし）
  - crawler を self.crawler に保存

open_spider(spider):
  - _items バッファをリセット（前回 spider の残骸を除去）
  - spider.spider_type でテーブル名を選択
  - テーブル名が空 → self.table = None（process_item は no-op）、info ログ
  - resolve_dynamodb_resource() でリソース取得 → self.table

_batch_flush(is_force=False):
  - table が None なら即 return（no-op）
  - len(_items) < batch_n かつ is_force でなければ return
  - snapshot: items, self._items = self._items, []（バッファをフラッシュ前にクリア）
  - batch_writer(overwrite_by_pkeys=[...]) でspider_type別PK指定
  - ItemAdapter(item).asdict() でdict変換して put_item
  - finally: sleep(put_delay)（エラー時も必ず実行）
  - 例外 → logger.error + stats.inc_value("errors") + raise DropItem

close_spider(spider):
  - _batch_flush(is_force=True)
  - self.table = None

process_item(item, spider):
  - table が None なら即 return item（no-op）
  - _items.append → _batch_flush() → return item
```

### ① Bitwarden 対応（_get_secret）

```python
def _get_secret(key: str) -> str | None:
    try:
        return _secrets_resolver.get(key)   # env: os.environ / bitwarden: BWS cache
    except SecretNotFound:
        return None                          # → boto3 デフォルト chain に委ねる

def resolve_dynamodb_resource(dynamodb_resource=None):
    if dynamodb_resource is not None:
        return dynamodb_resource             # テスト時モック注入
    return boto3.resource(
        "dynamodb",
        aws_access_key_id=_get_secret("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_get_secret("AWS_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("AWS_DEFAULT_REGION") or None,
    )
```

動作マトリクス:

| モード | 認証情報 | 挙動 |
|--------|----------|------|
| env | `.env` 設定済み | resolver → os.environ から取得 |
| env | 未設定 | SecretNotFound → None → boto3 default |
| bitwarden | BWS に登録済み | resolver → BWS cache から取得 |
| bitwarden | BWS 未登録 | SecretNotFound → None → IAM ロール等 |

### ② 新旧同時実行時の重複レコード

**重複は発生しない。** DynamoDB の put_item は PK (HASH+RANGE) ベースの upsert（上書き）。

PK 生成の新旧一致:

| spider_type | RANGE key 生成元 | 一致根拠 |
|---|---|---|
| transaction | HTML `data-table-sortable-value` 属性そのまま | 同一 HTML → 同一値 |
| asset_allocation | 同フォーマット `YYYYMMDD` + asset key | 同一ロジック |
| account | SHA256(`_join_strip(account_name)`) | コメントに「byte-identical to the legacy DynamoDB SK values」明記 |

`year_month_day` HASH key は採取日（観測日）。5/4 採取データと 5/5 採取データは別スナップショットであり、**意図的に別レコードとして格納される**（重複ではなく時系列データ）。

### ③ 実機検証で発覚したバグと対応（2026-05-05）

**バグ内容**: `_parsers.py` の `parse_transactions` で `year_month` にページ閲覧月を使用していた。

```python
# バグ: ページ月を使用
year_month = f"{year:04d}{month:02d}"  # year/month = spider が閲覧したページの年月
yield MoneyforwardTransactionItem(year_month=year_month, ...)

# 修正後: 実取引月を使用（旧 PJ と同一ロジック）
yield MoneyforwardTransactionItem(year_month=f"{y:04d}{mo:02d}", ...)
# y, mo = data_table_sortable_value から抽出した実取引日の年月
```

**影響**: ページ月 ≠ 実取引月のレコード（クレジットカード引き落とし月ズレ等）が旧 PJ と異なる `year_month` キーで書き込まれ、upsert にならず純増。

**対応**:
1. `_parsers.py` 修正（実取引月を使用）→ テスト 363件全パス確認
2. 不正レコード 111件を `data/delete_wrong_transactions.py --apply` で削除
3. 修正後コードで transaction spider 再実行 → before と完全一致（件数・内容とも）確認済み

**検証結果**:
- before（旧 PJ）: `202603`=246, `202604`=217, `202605`=8
- after（バグあり新 PJ）: `202603`=254, `202604`=250, `202605`=78（+111件）
- re-after（修正後新 PJ）: `202603`=246, `202604`=217, `202605`=8（完全一致・内容差分0件）

### overwrite_by_pkeys マッピング

```python
_PKEYS = {
    "transaction":      ["year_month",     "data_table_sortable_value"],
    "asset_allocation": ["year_month_day", "asset_item_key"],
    "account":          ["year_month_day", "account_item_key"],
}
```

同一 AWS batch（最大25件）内の PK 重複を後勝ちで排除。バッチ間の重複は DynamoDB の自然な upsert で解決。

### settings.py 変更

```python
ITEM_PIPELINES = {
    "moneyforward.pipelines.JsonArrayOutputPipeline": 300,
    "moneyforward.pipelines.DynamoDbPipeline": 400,
}

DYNAMODB_TABLE_NAME_TRANSACTION = os.environ.get("DYNAMODB_TABLE_NAME_TRANSACTION", "")
DYNAMODB_TABLE_NAME_ASSET_ALLOCATION = os.environ.get("DYNAMODB_TABLE_NAME_ASSET_ALLOCATION", "")
DYNAMODB_TABLE_NAME_ACCOUNT = os.environ.get("DYNAMODB_TABLE_NAME_ACCOUNT", "")
DYNAMODB_PUT_DELAY = float(os.environ.get("DYNAMODB_PUT_DELAY", "3"))
DYNAMODB_BATCH_N = int(os.environ.get("DYNAMODB_BATCH_N", "10"))
```

## タスク

- [x] `src/moneyforward/pipelines/` パッケージ化
  - `pipelines.py` → `pipelines/json_array.py` に移動
  - `pipelines/__init__.py` で `JsonArrayOutputPipeline` + `DynamoDbPipeline` re-export
- [x] `src/moneyforward/pipelines/dynamodb.py` 実装
  - `_get_secret` + `resolve_dynamodb_resource`（Bitwarden 対応）
  - `DynamoDbPipeline`（snapshot pattern、finally sleep、_batch_count 除去）
- [x] `src/moneyforward/settings.py` 更新（ITEM_PIPELINES + DYNAMODB_* 設定）
- [x] `.env.example` 更新（DYNAMODB_* + Bitwarden コメント追加）
- [x] `tests/test_dynamodb_pipeline_unit.py` 実装（32 tests）
  - 全テーブル名未設定 → `NotConfigured`
  - 空白のみ名前 → `NotConfigured`（strip fix）
  - open_spider: テーブル名空 → table=None（no-op）
  - open_spider: バッファリセット確認
  - バッチサイズ到達で flush + stats カウント
  - 複数 flush 跨ぎ（5 items / batch_n=2）
  - `close_spider` で残余 flush
  - snapshot pattern: エラー時もバッファクリア
  - エラー時 sleep 保証（finally）
  - エラー後 error stats カウント
  - エラー後バッファ汚染なし（次 item が新 batch を開始）
  - `DropItem` on DynamoDB error
  - 不明 spider_type で overwrite_by_pkeys なし
  - Scrapy hook シグネチャ確認（spider 引数）
  - Bitwarden mode: resolver 経由で認証情報取得
  - SecretNotFound → None → boto3 default
- [x] `pytest` 全パス確認（363 passed）

## 受け入れ基準

- 全 `DYNAMODB_TABLE_NAME_*` 未設定時: JSON のみ出力（既存動作維持）
- 設定時: JSON + DynamoDB（spider_type 対応テーブル）並列書き込み
- Bitwarden mode で AWS 認証情報を BWS から取得可能
- 新旧同時実行: 重複レコードなし（PK 衝突は upsert で解決）
- `pytest` 全パス

## ステータス

[完了 PR#69 2026-05-05]
