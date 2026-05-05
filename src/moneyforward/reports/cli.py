"""集計レポート CLI (``python -m moneyforward.reports``).

サブコマンド:

* ``balances`` — 月次収支レポート (元 PJ ``get_balances_report``)
* ``asset_allocation`` — アセットアロケーションレポート (元 PJ ``get_asset_allocation_report``)
* ``balances_csv`` — 年次収支 CSV (元 PJ ``get_balances_csv``)
* ``blog_balances`` — ブログ向け収支 Markdown (元 PJ ``get_balances_blog``)
* ``blog_asset_allocation`` — ブログ向け資産配分 Markdown (元 PJ ``get_asset_allocation_blog``)

入力は ``--input-dir`` (既定: ``runtime/output``) 配下の JSONL。
``--slack`` を付けない限り標準出力にのみ書き出す (副作用安全)。
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

from moneyforward.reports import asset_allocation as aa_mod
from moneyforward.reports import balances as bal_mod
from moneyforward.reports._loader import (
    filter_year_month,
    filter_year_month_day,
    load_output_json,
)
from moneyforward.reports.blog_asset_allocation import report_blog_asset_allocation
from moneyforward.reports.blog_balances import (
    load_account_types,
    report_blog_balances,
    report_cost_of_living,
)
from moneyforward.reports.segregated_asset import (
    apply_adjustments,
    compute_adjustments,
    load_segregated_config,
)
from moneyforward.utils.slack_notifier import SlackNotifier

_DEFAULT_SEGREGATED_CONFIG = Path("config/segregated_asset.yaml")
_DEFAULT_ACCOUNT_TYPES_CONFIG = Path("config/account_types.yaml")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m moneyforward.reports",
        description="集計レポート生成 (JSONL 入力)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("runtime/output"),
        help="JSONL 入力ディレクトリ (既定: runtime/output)",
    )
    parser.add_argument(
        "--slack",
        action="store_true",
        help="SLACK_INCOMING_WEBHOOK_URL に投稿する (既定: 標準出力のみ)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_bal = sub.add_parser("balances", help="月次収支レポート")
    p_bal.add_argument("-y", "--year", type=int, required=True)
    p_bal.add_argument("-m", "--month", type=int, required=True)
    p_bal.add_argument(
        "--detail",
        action="store_true",
        help="大項目/中項目内訳を表示 (既定: サマリのみ)",
    )

    p_aa = sub.add_parser("asset_allocation", help="アセットアロケーションレポート")
    p_aa.add_argument("-y", "--year", type=int, required=True)
    p_aa.add_argument("-m", "--month", type=int, required=True)
    p_aa.add_argument("-d", "--day", type=int, required=True)
    p_aa.add_argument(
        "--segregated-config",
        type=Path,
        default=_DEFAULT_SEGREGATED_CONFIG,
        dest="segregated_config",
        help=f"分別管理資産・借入控除定義 YAML (既定: {_DEFAULT_SEGREGATED_CONFIG})",
    )
    p_aa.add_argument(
        "--no-segregated-config",
        action="store_true",
        dest="no_segregated_config",
        help="分別管理・借入控除を適用しない (比較・デバッグ用)",
    )

    p_csv = sub.add_parser("balances_csv", help="年次収支 CSV")
    p_csv.add_argument("-y", "--year", type=int, required=True)
    p_csv.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="出力 CSV パス",
    )

    p_bb = sub.add_parser(
        "blog_balances", help="ブログ向け収支 Markdown (Google Charts)"
    )
    p_bb.add_argument("-y", "--year", type=int, required=True)
    p_bb.add_argument("-m", "--month", type=int, required=True)
    p_bb.add_argument(
        "--cost",
        action="store_true",
        help="生活費収支分析（変動費/固定費）テーブルを出力",
    )
    p_bb.add_argument(
        "--account-types-config",
        type=Path,
        default=_DEFAULT_ACCOUNT_TYPES_CONFIG,
        dest="account_types_config",
        help=f"口座種別分類 YAML (既定: {_DEFAULT_ACCOUNT_TYPES_CONFIG})",
    )

    p_baa = sub.add_parser(
        "blog_asset_allocation",
        help="ブログ向け資産配分 Markdown (Google Charts)",
    )
    p_baa.add_argument("-y", "--year", type=int, required=True)
    p_baa.add_argument("-m", "--month", type=int, required=True)
    p_baa.add_argument("-d", "--day", type=int, required=True)
    p_baa.add_argument(
        "--segregated-config",
        type=Path,
        default=_DEFAULT_SEGREGATED_CONFIG,
        dest="segregated_config",
        help=f"分別管理資産定義 YAML (既定: {_DEFAULT_SEGREGATED_CONFIG})",
    )
    p_baa.add_argument(
        "--no-segregated-config",
        action="store_true",
        dest="no_segregated_config",
        help="分別管理調整を適用しない",
    )

    return parser


def _cmd_balances(args: argparse.Namespace) -> str:
    items = list(load_output_json(args.input_dir, "transaction"))
    monthly = list(filter_year_month(items, args.year, args.month))
    aggregated = bal_mod.aggregate_balances(monthly)
    return bal_mod.report_message(
        aggregated, args.year, args.month, is_summary=not args.detail
    )


def _cmd_asset_allocation(args: argparse.Namespace) -> str:
    items = list(load_output_json(args.input_dir, "asset_allocation"))
    daily = list(filter_year_month_day(items, args.year, args.month, args.day))
    aggregated = aa_mod.aggregate_asset_allocation(daily)

    if not getattr(args, "no_segregated_config", False):
        cfg_path: Path = args.segregated_config
        if not cfg_path.exists():
            if cfg_path == _DEFAULT_SEGREGATED_CONFIG:
                logger.warning(
                    "分別管理資産定義ファイルが見つかりません: %s "
                    "(example をコピーして作成: copy config/segregated_asset.example.yaml config/segregated_asset.yaml)",
                    cfg_path,
                )
            else:
                raise FileNotFoundError(
                    f"--segregated-config で指定されたファイルが存在しません: {cfg_path}"
                )
        cfg = load_segregated_config(cfg_path)
        adj = compute_adjustments(cfg, date(args.year, args.month, args.day))
        aggregated = apply_adjustments(aggregated, adj)

    return aa_mod.report_message(aggregated, args.year, args.month, args.day)


def _cmd_blog_balances(args: argparse.Namespace) -> str:
    items = list(load_output_json(args.input_dir, "transaction"))
    if args.cost:
        return report_cost_of_living(items, args.year, args.month)

    monthly = list(filter_year_month(items, args.year, args.month))
    account_types = load_account_types(args.account_types_config)
    return report_blog_balances(monthly, args.year, args.month, account_types)


def _cmd_blog_asset_allocation(args: argparse.Namespace) -> str:
    items = list(load_output_json(args.input_dir, "asset_allocation"))

    segregated_config: dict | None = None
    if not getattr(args, "no_segregated_config", False):
        cfg_path: Path = args.segregated_config
        if not cfg_path.exists():
            if cfg_path == _DEFAULT_SEGREGATED_CONFIG:
                logger.warning(
                    "分別管理資産定義ファイルが見つかりません: %s "
                    "(example をコピーして作成: "
                    "copy config/segregated_asset.example.yaml config/segregated_asset.yaml)",
                    cfg_path,
                )
            else:
                raise FileNotFoundError(
                    f"--segregated-config で指定されたファイルが存在しません: {cfg_path}"
                )
        else:
            segregated_config = load_segregated_config(cfg_path)

    return report_blog_asset_allocation(
        items, args.year, args.month, args.day, segregated_config
    )


def _cmd_balances_csv(args: argparse.Namespace) -> str:
    items = list(load_output_json(args.input_dir, "transaction"))
    monthly_aggregates: dict[int, dict] = {}
    for month in range(1, 13):
        m_items = list(filter_year_month(items, args.year, month))
        if m_items:
            monthly_aggregates[month] = bal_mod.aggregate_balances(m_items)
    csv_text = bal_mod.report_csv(monthly_aggregates, args.year)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # 元 PJ と同じく BOM 付き UTF-8 (Excel 互換)
    args.output.write_text(csv_text, encoding="utf-8-sig", newline="")
    return f"wrote {args.output} ({len(csv_text)} bytes)"


def main(argv: list[str] | None = None) -> int:
    """CLI エントリーポイント.

    Parameters
    ----------
    argv : list[str] | None
        引数 (既定: ``sys.argv[1:]``)。

    Returns
    -------
    int
        終了コード (0=成功)。
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "balances":
        message = _cmd_balances(args)
    elif args.command == "asset_allocation":
        message = _cmd_asset_allocation(args)
    elif args.command == "balances_csv":
        message = _cmd_balances_csv(args)
    elif args.command == "blog_balances":
        message = _cmd_blog_balances(args)
    elif args.command == "blog_asset_allocation":
        message = _cmd_blog_asset_allocation(args)
    else:
        parser.error(f"unknown command: {args.command}")
        return 2

    sys.stdout.write(message)
    if not message.endswith("\n"):
        sys.stdout.write("\n")
    if args.slack:
        SlackNotifier().notify(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
