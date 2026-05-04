"""証券会社 CSV → 集計済配当 CSV 変換の高水準 API.

ファイル名 prefix で証券会社を自動判別し、cp932 / utf-8 を順に試行する.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable

from moneyforward.seccsv import _parsers as P

# (filename_prefix, encoding, parser)
BROKER_RULES: tuple[tuple[str, str, Callable[..., dict[str, int]]], ...] = (
    ("specificaccountpl_", "cp932", P.parse_rakutensec_profit_and_loss),
    ("DetailInquiry_", "utf-8", P.parse_sbisec_withdrawal_detail),
    ("New_file_", "utf-8", P.parse_nomurasec_all_transaction),
    ("SaveFile_", "cp932", P.parse_sbisec_transfer_tax_detail),
)


def _read_csv(path: Path, encoding: str) -> list[list[str]]:
    """指定エンコーディングで CSV を読み出す.

    cp932 で失敗した場合は utf-8 へフォールバック (元 PJ ファイルの混在対応).
    """
    encodings = [encoding]
    if encoding != "utf-8":
        encodings.append("utf-8")
    last_exc: Exception | None = None
    for enc in encodings:
        try:
            with path.open("r", encoding=enc, newline="") as f:
                return list(csv.reader(f))
        except UnicodeDecodeError as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    return []


def detect_broker(
    filename: str,
) -> tuple[str, Callable[..., dict[str, int]]] | None:
    """ファイル名 prefix から ``(encoding, parser)`` を返す.

    Parameters
    ----------
    filename : str
        判定対象のファイル名 (basename 想定).

    Returns
    -------
    tuple[str, Callable] | None
        ``(encoding, parser_func)``. 該当なしの場合は ``None``.
    """
    for prefix, encoding, parser in BROKER_RULES:
        if filename.startswith(prefix):
            return encoding, parser
    return None


def convert(input_dir: Path, output_path: Path) -> int:
    """``input_dir`` 配下の証券会社 CSV を全て読み、月次集計 CSV を出力する.

    Parameters
    ----------
    input_dir : Path
        証券会社ダウンロード CSV を配置したディレクトリ.
    output_path : Path
        出力 CSV パス. 親ディレクトリは無ければ自動作成.

    Returns
    -------
    int
        出力した行数 (ヘッダ除く).
    """
    if not input_dir.exists():
        raise FileNotFoundError(input_dir)

    monthly_sources: list[dict[str, int]] = []
    for entry in sorted(input_dir.iterdir()):
        if not entry.is_file() or entry.suffix.lower() != ".csv":
            continue
        match = detect_broker(entry.name)
        if match is None:
            continue
        encoding, parser = match
        rows = _read_csv(entry, encoding)
        monthly_sources.append(parser(rows))

    merged = P.merge_monthly(*monthly_sources)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["集計期間", "配当金・金利収入"])
        for key in sorted(merged.keys()):
            writer.writerow([key, merged[key]])
            written += 1
    return written
