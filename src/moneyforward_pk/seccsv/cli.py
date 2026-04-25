"""``python -m moneyforward_pk.seccsv`` CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from moneyforward_pk.seccsv.converter import convert


def main(argv: list[str] | None = None) -> int:
    """CLI エントリーポイント."""
    parser = argparse.ArgumentParser(
        prog="python -m moneyforward_pk.seccsv",
        description="証券会社ダウンロード CSV → 集計配当 CSV 変換",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_conv = sub.add_parser("convert", help="CSV 群を集計してファイル出力")
    p_conv.add_argument("--input", type=Path, required=True, help="入力ディレクトリ")
    p_conv.add_argument("--output", type=Path, required=True, help="出力 CSV パス")

    args = parser.parse_args(argv)
    if args.command == "convert":
        count = convert(args.input, args.output)
        sys.stdout.write(f"wrote {args.output} ({count} months)\n")
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
