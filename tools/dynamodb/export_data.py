"""DynamoDB データエクスポートツール.

全3テーブルを年月単位で Query し runtime/output/export/ 以下に JSON 保存。
Full Scan 不使用。レートリミット対策として月単位ループ間に delay を挟む。

テーブル → フォルダ対応:
  transaction    (PK: year_month)      -> exports/transactions/YYYY-MM.json
  asset_allocation (PK: year_month_day) -> exports/assets/YYYY-MM.json
  account        (PK: year_month_day)  -> exports/accounts/YYYY-MM.json

asset_allocation / account は HASH Key が year_month_day のため begins_with 不可。
日ごとに Query してまとめる。

環境変数:
  DYNAMODB_TABLE_NAME_TRANSACTION
  DYNAMODB_TABLE_NAME_ASSET_ALLOCATION
  DYNAMODB_TABLE_NAME_ACCOUNT
  AWS_DEFAULT_REGION        (任意)
  AWS_ACCESS_KEY_ID         (任意)
  AWS_SECRET_ACCESS_KEY     (任意)
  SECRETS_BACKEND           (任意; "env" | "bitwarden")

実行例:
  .venv-win/Scripts/python.exe tools/dynamodb/export_data.py --year-month 2024-03
  .venv-win/Scripts/python.exe tools/dynamodb/export_data.py --year 2024
  .venv-win/Scripts/python.exe tools/dynamodb/export_data.py --from 2024-01 --to 2024-06
  .venv-win/Scripts/python.exe tools/dynamodb/export_data.py --year 2024 --dry-run
"""

from __future__ import annotations

import argparse
import calendar
import json
import logging
import os
import re
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

_YM_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)

_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from moneyforward.secrets import resolver as _secrets_resolver  # noqa: E402
from moneyforward.secrets.exceptions import SecretNotFound  # noqa: E402

logger = logging.getLogger(__name__)

_OUTPUT_BASE = _PROJECT_ROOT / "runtime" / "output" / "export"

_TABLE_ENV_VARS: dict[str, str] = {
    "transaction": "DYNAMODB_TABLE_NAME_TRANSACTION",
    "asset_allocation": "DYNAMODB_TABLE_NAME_ASSET_ALLOCATION",
    "account": "DYNAMODB_TABLE_NAME_ACCOUNT",
}

_EXPORT_FOLDERS: dict[str, str] = {
    "transaction": "transactions",
    "asset_allocation": "assets",
    "account": "accounts",
}

# asset_allocation / account の HASH Key 属性名
_DAY_PK_ATTR: dict[str, str] = {
    "asset_allocation": "year_month_day",
    "account": "year_month_day",
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
    names = {t: os.environ.get(env, "").strip() for t, env in _TABLE_ENV_VARS.items()}
    if not any(names.values()):
        sys.exit(
            "エラー: テーブル名 env var が全て未設定。"
            f"({', '.join(_TABLE_ENV_VARS.values())}) のいずれかを設定してください。"
        )
    return names


def _parse_year_months(args: argparse.Namespace) -> list[str]:
    if args.year_month:
        return [args.year_month]
    if args.year:
        return [f"{args.year}-{m:02d}" for m in range(1, 13)]
    # --from / --to
    result: list[str] = []
    y, m = int(args.from_ym[:4]), int(args.from_ym[5:])
    ty, tm = int(args.to_ym[:4]), int(args.to_ym[5:])
    while (y, m) <= (ty, tm):
        result.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return result


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _query_all(table: Any, key_condition: Any) -> list[dict]:
    """ページネーション込み Query。."""
    items: list[dict] = []
    kwargs: dict[str, Any] = {"KeyConditionExpression": key_condition}
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def _fetch_transaction(table: Any, year_month: str) -> list[dict]:
    # DynamoDB PK format: "YYYYMM" (no hyphens)
    from boto3.dynamodb.conditions import Key

    pk_val = year_month.replace("-", "")
    return _query_all(table, Key("year_month").eq(pk_val))


def _fetch_by_day(table: Any, year_month: str, pk_attr: str) -> list[dict]:
    """HASH Key が year_month_day のテーブル用: 日ごとに Query してまとめる。.

    DynamoDB PK format: "YYYYMMDD" (no hyphens).
    """
    from boto3.dynamodb.conditions import Key

    year, month = int(year_month[:4]), int(year_month[5:])
    days = calendar.monthrange(year, month)[1]
    items: list[dict] = []
    for day in range(1, days + 1):
        pk_val = f"{year:04d}{month:02d}{day:02d}"
        items.extend(_query_all(table, Key(pk_attr).eq(pk_val)))
    return items


def _export_month(
    db: Any,
    table_names: dict[str, str],
    year_month: str,
    output_base: Path,
    table_filter: list[str] | None,
    no_overwrite: bool,
    dry_run: bool,
) -> bool:
    """1年月分エクスポート。エラーあり→ False。."""
    ok = True
    for table_type, folder in _EXPORT_FOLDERS.items():
        if table_filter and folder not in table_filter:
            continue

        table_name = table_names.get(table_type, "")
        if not table_name:
            logger.info("skip (env unset): %s", _TABLE_ENV_VARS[table_type])
            continue

        out_dir = output_base / folder
        out_path = out_dir / f"{year_month}.json"

        if no_overwrite and out_path.exists():
            logger.info("skip (exists): %s", out_path)
            continue

        if dry_run:
            logger.info("[DRY-RUN] %s/%s -> %s", table_name, year_month, out_path)
            continue

        try:
            table = db.Table(table_name)
            if table_type == "transaction":
                items = _fetch_transaction(table, year_month)
            else:
                items = _fetch_by_day(table, year_month, _DAY_PK_ATTR[table_type])

            out_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = out_path.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(items, ensure_ascii=False, default=_json_default, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(out_path)
            try:
                display = out_path.relative_to(_PROJECT_ROOT)
            except ValueError:
                display = out_path
            logger.info("saved: %s (%d items)", display, len(items))
        except Exception as err:
            from botocore.exceptions import ClientError  # type: ignore[import]

            if isinstance(err, ClientError):
                code = err.response["Error"]["Code"]
                if code in {
                    "UnrecognizedClientException",
                    "ExpiredTokenException",
                    "InvalidSignatureException",
                    "AccessDeniedException",
                }:
                    raise
            logger.error("failed: %s %s — %s", table_name, year_month, err)
            ok = False
    return ok


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="DynamoDB データエクスポート")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--year-month", metavar="YYYY-MM", help="特定年月のみ")
    group.add_argument(
        "--year", type=int, metavar="YYYY", help="年指定（1〜12月を順次取得）"
    )
    group.add_argument(
        "--from", dest="from_ym", metavar="YYYY-MM", help="範囲開始（--to と併用）"
    )

    parser.add_argument(
        "--to", dest="to_ym", metavar="YYYY-MM", help="範囲終了（--from と併用）"
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        choices=list(_EXPORT_FOLDERS.values()),
        help="対象テーブル絞り込み",
    )
    parser.add_argument(
        "--delay-sec",
        type=float,
        default=2.0,
        metavar="SEC",
        help="月間 delay 秒数（デフォルト: 2.0）",
    )
    parser.add_argument(
        "--no-overwrite", action="store_true", help="既存ファイルをスキップ"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="取得・保存せず内容確認のみ"
    )

    args = parser.parse_args()

    if args.from_ym and not args.to_ym:
        parser.error("--from には --to が必要")
    if args.to_ym and not args.from_ym:
        parser.error("--to には --from が必要")

    for flag, val in [
        ("--year-month", args.year_month),
        ("--from", args.from_ym),
        ("--to", args.to_ym),
    ]:
        if val and not _YM_RE.match(val):
            parser.error(f"{flag} は YYYY-MM 形式で指定してください（例: 2024-03）")

    year_months = _parse_year_months(args)
    if not year_months:
        parser.error("対象年月が空。引数を確認してください。")

    table_names = _resolve_table_names()
    db = None if args.dry_run else _build_resource()

    logger.info(
        "対象: %d ヶ月  delay: %.1fs  dry_run: %s",
        len(year_months),
        args.delay_sec,
        args.dry_run,
    )

    failed = False
    for i, ym in enumerate(year_months):
        logger.info("=== %s ===", ym)
        ok = _export_month(
            db,
            table_names,
            ym,
            _OUTPUT_BASE,
            args.tables,
            args.no_overwrite,
            args.dry_run,
        )
        if not ok:
            failed = True
        if i < len(year_months) - 1 and not args.dry_run:
            logger.info("delay %.1fs...", args.delay_sec)
            time.sleep(args.delay_sec)

    logger.info("完了。%s", "エラーあり" if failed else "正常終了")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
