"""DynamoDB テーブル初期設定ツール.

新 PJ の 3 テーブルを PAY_PER_REQUEST で作成する。
テーブル名は環境変数から読み込み、未設定のテーブルはスキップ。
既存テーブルは ResourceInUseException をキャッチしてスキップ（べき等）。
既存テーブルのキースキーマが想定と異なる場合は WARNING ログを出す。
テーブル名重複は事前に検知して中断する。

環境変数:
  DYNAMODB_TABLE_NAME_TRANSACTION
  DYNAMODB_TABLE_NAME_ASSET_ALLOCATION
  DYNAMODB_TABLE_NAME_ACCOUNT
  AWS_DEFAULT_REGION        (任意; 未設定時は boto3 デフォルト)
  AWS_ACCESS_KEY_ID         (任意; 未設定時は boto3 デフォルト連鎖)
  AWS_SECRET_ACCESS_KEY     (任意; 未設定時は boto3 デフォルト連鎖)
  SECRETS_BACKEND           (任意; "env" | "bitwarden", デフォルト "env")

実行方法:
  .venv-win/Scripts/python.exe tools/dynamodb/setup_tables.py [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)

_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from moneyforward.secrets import resolver as _secrets_resolver  # noqa: E402
from moneyforward.secrets.exceptions import SecretNotFound  # noqa: E402

logger = logging.getLogger(__name__)

# pipelines/dynamodb.py の _PKEYS と同一設計（PK/SK 変更時は両方更新）。
_TABLE_SCHEMA: dict[str, tuple[str, str]] = {
    "transaction": ("year_month", "data_table_sortable_value"),
    "asset_allocation": ("year_month_day", "asset_item_key"),
    "account": ("year_month_day", "account_item_key"),
}

_TABLE_ENV_VARS: dict[str, str] = {
    "transaction": "DYNAMODB_TABLE_NAME_TRANSACTION",
    "asset_allocation": "DYNAMODB_TABLE_NAME_ASSET_ALLOCATION",
    "account": "DYNAMODB_TABLE_NAME_ACCOUNT",
}


def _get_secret(key: str) -> str | None:
    try:
        return _secrets_resolver.get(key)
    except SecretNotFound:
        return None


def _build_resource() -> Any:
    import boto3  # type: ignore[import]

    return boto3.resource(
        "dynamodb",
        aws_access_key_id=_get_secret("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_get_secret("AWS_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("AWS_DEFAULT_REGION") or None,
    )


def _resolve_table_names() -> dict[str, str]:
    return {
        table_type: os.environ.get(env_var, "").strip()
        for table_type, env_var in _TABLE_ENV_VARS.items()
    }


def _validate_unique(table_names: dict[str, str]) -> None:
    seen: dict[str, str] = {}
    for table_type, name in table_names.items():
        if not name:
            continue
        if name in seen:
            sys.exit(
                f"エラー: テーブル名重複 — '{name}' が "
                f"{seen[name]} と {table_type} の両方に設定されている"
            )
        seen[name] = table_type


def _validate_existing_schema(
    db: Any, table_name: str, expected_pk: str, expected_sk: str
) -> None:
    table = db.Table(table_name)
    table.load()
    actual = {k["KeyType"]: k["AttributeName"] for k in table.key_schema}
    if actual.get("HASH") != expected_pk or actual.get("RANGE") != expected_sk:
        logger.warning(
            "スキーマ不一致: %s — 期待 (HASH=%s, RANGE=%s)  実際 (HASH=%s, RANGE=%s)",
            table_name,
            expected_pk,
            expected_sk,
            actual.get("HASH"),
            actual.get("RANGE"),
        )


def _print_plan(table_names: dict[str, str]) -> None:
    named = [n for n in table_names.values() if n]
    width = max((len(n) for n in named), default=0)
    logger.info("[DRY-RUN] 作成予定テーブル:")
    for table_type, (pk, sk) in _TABLE_SCHEMA.items():
        table_name = table_names[table_type]
        env_var = _TABLE_ENV_VARS[table_type]
        if not table_name:
            logger.info("  SKIP   (%s 未設定)", env_var)
        else:
            logger.info("  CREATE %-*s  PK=%s  SK=%s", width, table_name, pk, sk)


def _create_table(db: Any, table_name: str, pk: str, sk: str) -> str:
    """テーブル作成。戻り値は "created" | "exists"。."""
    from botocore.exceptions import ClientError  # type: ignore[import]

    try:
        table = db.create_table(
            TableName=table_name,
            AttributeDefinitions=[
                {"AttributeName": pk, "AttributeType": "S"},
                {"AttributeName": sk, "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": pk, "KeyType": "HASH"},
                {"AttributeName": sk, "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        return "created"
    except ClientError as err:
        if err.response["Error"]["Code"] == "ResourceInUseException":
            _validate_existing_schema(db, table_name, pk, sk)
            return "exists"
        raise


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="DynamoDB テーブル初期設定")
    parser.add_argument("--dry-run", action="store_true", help="作成せず内容確認のみ")
    args = parser.parse_args()

    table_names = _resolve_table_names()
    _validate_unique(table_names)

    if args.dry_run:
        _print_plan(table_names)
        logger.info("[DRY-RUN] 完了。変更なし。")
        return

    db = _build_resource()
    created = exists = skipped = failed = 0

    for table_type, (pk, sk) in _TABLE_SCHEMA.items():
        table_name = table_names[table_type]
        env_var = _TABLE_ENV_VARS[table_type]

        if not table_name:
            logger.info("skip (env unset): %s", env_var)
            skipped += 1
            continue

        try:
            result = _create_table(db, table_name, pk, sk)
        except Exception as err:
            logger.error("create_table failed: %s — %s", table_name, err)
            failed += 1
            continue

        if result == "created":
            logger.info("created: %s  (PK=%s, SK=%s)", table_name, pk, sk)
            created += 1
        else:
            logger.info("exists (skip): %s", table_name)
            exists += 1

    logger.info(
        "完了 — created=%d  exists=%d  skipped=%d  failed=%d",
        created,
        exists,
        skipped,
        failed,
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
