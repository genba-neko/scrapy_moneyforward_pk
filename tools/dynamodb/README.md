# tools/dynamodb

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
