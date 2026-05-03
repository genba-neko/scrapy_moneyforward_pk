"""集計レポート CLI (``python -m moneyforward_pk.reports``).

サブコマンド:

* ``balances`` — 月次収支レポート (元 PJ ``get_balances_report``)
* ``asset_allocation`` — アセットアロケーションレポート (元 PJ ``get_asset_allocation_report``)
* ``balances_csv`` — 年次収支 CSV (元 PJ ``get_balances_csv``)

入力は ``--input-dir`` (既定: ``runtime/output``) 配下の JSONL。
``--slack`` を付けない限り標準出力にのみ書き出す (副作用安全)。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from moneyforward_pk.reports import asset_allocation as aa_mod
from moneyforward_pk.reports import balances as bal_mod
from moneyforward_pk.reports._loader import (
    filter_year_month,
    filter_year_month_day,
    load_output_json,
)
from moneyforward_pk.utils.slack_notifier import SlackNotifier


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m moneyforward_pk.reports",
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

    p_csv = sub.add_parser("balances_csv", help="年次収支 CSV")
    p_csv.add_argument("-y", "--year", type=int, required=True)
    p_csv.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="出力 CSV パス",
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
    return aa_mod.report_message(aggregated, args.year, args.month, args.day)


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
