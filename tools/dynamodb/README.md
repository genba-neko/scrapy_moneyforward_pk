# tools/dynamodb

DynamoDB 関連ツール集。

| ツール | 概要 |
|---|---|
| `setup_tables.py` | テーブル初期作成（べき等） |
| `export_data.py` | テーブルデータを年月単位でエクスポート |

---

## export_data.py

DynamoDB 全3テーブルのデータを年月単位で Query し JSON ファイルとして保存するツール。
Full Scan 不使用。月単位ループ間に delay を挟みレートリミットに配慮。

### 保存先

```
runtime/output/export/
  transactions/   <- transaction テーブル
    YYYY-MM.json
  assets/         <- asset_allocation テーブル
    YYYY-MM.json
  accounts/       <- account テーブル
    YYYY-MM.json
```

### 実行例

```bash
# 特定年月
.venv-win/Scripts/python.exe tools/dynamodb/export_data.py --year-month 2024-03

# 年指定（1〜12月を順次取得）
.venv-win/Scripts/python.exe tools/dynamodb/export_data.py --year 2024

# 範囲指定
.venv-win/Scripts/python.exe tools/dynamodb/export_data.py --from 2024-01 --to 2024-06

# テーブル絞り込み
.venv-win/Scripts/python.exe tools/dynamodb/export_data.py --year 2024 --tables transactions assets

# delay 調整（デフォルト 2.0 秒）
.venv-win/Scripts/python.exe tools/dynamodb/export_data.py --year 2024 --delay-sec 5

# 既存ファイルをスキップ
.venv-win/Scripts/python.exe tools/dynamodb/export_data.py --year 2024 --no-overwrite

# dry-run（取得・保存なし）
.venv-win/Scripts/python.exe tools/dynamodb/export_data.py --year 2024 --dry-run
```

### 動作仕様

- `transaction`: `year_month = "YYYY-MM"` で Query（1クエリ/月）
- `asset_allocation` / `account`: `year_month_day = "YYYY-MM-DD"` で日ごとに Query（最大31クエリ/月）
  - HASH Key への `begins_with` は DynamoDB 非対応のため日ループで代替
- 0件の年月も空配列 `[]` でファイル生成
- 既存ファイルは上書き（`--no-overwrite` でスキップ）
- テーブル名 env var 未設定のテーブルはスキップ
- 失敗月は ERROR ログ + 継続し、最後に `exit 1`

---

## setup_tables.py

DynamoDB テーブル初期設定ツール。新 PJ の 3 テーブルを作成する。

## 前提

- Python 仮想環境 `.venv-win` がセットアップ済みであること
- AWS 認証情報が設定済みであること（env var / `~/.aws/config` / IAM ロール）

## 環境変数

### テーブル名（作成対象を絞りたい場合は未設定のままにする）

| 変数名 | 対応テーブル |
|--------|-------------|
| `DYNAMODB_TABLE_NAME_TRANSACTION` | 取引 |
| `DYNAMODB_TABLE_NAME_ASSET_ALLOCATION` | 資産内訳 |
| `DYNAMODB_TABLE_NAME_ACCOUNT` | 口座 |

### AWS 認証情報

| 変数名 | 説明 |
|--------|------|
| `AWS_DEFAULT_REGION` | リージョン（例: `ap-northeast-1`）|
| `AWS_ACCESS_KEY_ID` | アクセスキー（未設定時は boto3 デフォルト連鎖）|
| `AWS_SECRET_ACCESS_KEY` | シークレットキー（未設定時は boto3 デフォルト連鎖）|
| `SECRETS_BACKEND` | `env`（デフォルト）または `bitwarden` |

プロジェクトルートの `.env` を自動ロードする。

## テーブル設計

| テーブル種別 | PK (HASH) | SK (RANGE) | BillingMode |
|-------------|-----------|------------|-------------|
| transaction | `year_month` (S) | `data_table_sortable_value` (S) | PAY_PER_REQUEST |
| asset_allocation | `year_month_day` (S) | `asset_item_key` (S) | PAY_PER_REQUEST |
| account | `year_month_day` (S) | `account_item_key` (S) | PAY_PER_REQUEST |

## 実行方法

```bash
# 内容確認（作成しない）
.venv-win/Scripts/python.exe tools/dynamodb/setup_tables.py --dry-run

# 実際に作成
.venv-win/Scripts/python.exe tools/dynamodb/setup_tables.py
```

## 動作仕様

- テーブル名 env var が未設定のテーブルはスキップ
- 複数の env var に同じテーブル名が設定されている場合は起動時にエラーで中断
- すでに存在するテーブルは `ResourceInUseException` をキャッチしてスキップ（べき等）
  - 既存テーブルのキースキーマが想定と異なる場合は WARNING ログを出力
- テーブル作成後は `wait_until_exists()` で ACTIVE 化を確認してから次へ進む
- 個別テーブルの作成失敗は ERROR ログを出して次のテーブルを処理し、最後に `exit 1`
- `--dry-run` では AWS への接続を行わず、作成予定内容をログ出力して終了
