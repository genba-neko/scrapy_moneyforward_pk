"""証券会社別 CSV パーサー (純関数).

各証券会社のダウンロード CSV を行のリストに開いてから渡し、
``{"YYYY/MM": int}`` 形式の月次集計 dict を返す.

ファイル名 prefix から証券会社を自動判別する高水準 API は
``converter.detect_broker`` を参照.
"""

from __future__ import annotations

import datetime as _dt
from typing import Iterable


def _to_year_month(date_str: str, fmt: str) -> str:
    """``date_str`` を ``YYYY/MM`` キーへ正規化する."""
    return _dt.datetime.strptime(date_str, fmt).strftime("%Y/%m")


def _safe_int(token: str) -> int:
    """カンマ・``+``・空白・``-`` 単独 (= 0) を吸収して int 化する."""
    cleaned = token.replace(",", "").replace("+", "").strip()
    if cleaned in ("", "-"):
        return 0
    return int(cleaned)


def parse_sbisec_transfer_tax_detail(rows: Iterable[list[str]]) -> dict[str, int]:
    """SBI 証券「譲渡益税明細」CSV → 月次税引後配当 dict.

    Parameters
    ----------
    rows : Iterable[list[str]]
        ``csv.reader`` が返す行イテラブル.

    Returns
    -------
    dict[str, int]
        ``{"YYYY/MM": tax_adjusted_dividend}``.
    """
    income: dict[str, int] = {}
    tax: dict[str, int] = {}
    last_key: str | None = None
    for row in rows:
        if len(row) == 12 and ("配当金" in row[5] or "債券利金" in row[5]):
            key = _to_year_month(row[6], "%Y/%m/%d")
            income[key] = income.get(key, 0) + _safe_int(row[11])
            last_key = key
        elif len(row) == 13 and "税徴収額" in row[0] and last_key is not None:
            # 税徴収行は前行の配当に紐づく扱い (元 PJ 仕様)
            tax[last_key] = tax.get(last_key, 0) + _safe_int(row[11]) + _safe_int(row[12])
    return _net_income(income, tax)


def parse_rakutensec_profit_and_loss(rows: Iterable[list[str]]) -> dict[str, int]:
    """楽天証券「特定口座損益 (年間合計月次履歴)」CSV → 月次税引後配当 dict."""
    income: dict[str, int] = {}
    tax: dict[str, int] = {}
    for row in rows:
        if len(row) == 7 and "月" not in row[0]:
            try:
                key = _to_year_month(row[0], "%Y/%m")
            except ValueError:
                continue
            income[key] = income.get(key, 0) + _safe_int(row[1]) + _safe_int(row[4])
            tax[key] = tax.get(key, 0) + _safe_int(row[2]) + _safe_int(row[5])
    return _net_income(income, tax)


def parse_sbisec_withdrawal_detail(rows: Iterable[list[str]]) -> dict[str, int]:
    """SBI 証券「入出金明細」CSV → 月次配当 dict (税は引かれない)."""
    income: dict[str, int] = {}
    for row in rows:
        if len(row) == 7 and row[1] == "入金" and ("配当金" in row[2] or "貸株金利" in row[2]):
            try:
                key = _to_year_month(row[0], "%Y/%m/%d")
            except ValueError:
                continue
            income[key] = income.get(key, 0) + _safe_int(row[4])
    return income


def parse_nomurasec_all_transaction(rows: Iterable[list[str]]) -> dict[str, int]:
    """野村證券「すべての取引履歴」CSV → 月次配当 dict."""
    income: dict[str, int] = {}
    for row in rows:
        if len(row) >= 12 and "配当金" in row[6]:
            try:
                key = _to_year_month(row[1], "%Y/%m/%d")
            except ValueError:
                continue
            income[key] = income.get(key, 0) + _safe_int(row[11])
    return income


def _net_income(income: dict[str, int], tax: dict[str, int]) -> dict[str, int]:
    """``income`` から ``tax`` を引いた月次 dict を返す純関数."""
    return {key: amount - tax.get(key, 0) for key, amount in income.items()}


def merge_monthly(*sources: dict[str, int]) -> dict[str, int]:
    """複数証券会社の月次 dict を加算マージする."""
    merged: dict[str, int] = {}
    for source in sources:
        for key, amount in source.items():
            merged[key] = merged.get(key, 0) + amount
    return merged
