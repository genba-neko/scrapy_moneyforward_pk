"""収支集計レポート (元 PJ ``get_balances_report`` 相当).

JSONL の transaction レコードを大項目 (lctg) / 中項目 (mctg) で集計し、
Slack 風テキストや CSV 形式に整形する純関数群。
"""

from __future__ import annotations

import csv
import io
from typing import Iterable

# 元 PJ の ``get_balances_report.py`` のデフォルト除外設定
DEFAULT_EXCLUDE_LCTG: tuple[str, ...] = ("現金・カード",)
DEFAULT_EXCLUDE_MCTG: tuple[str, ...] = (
    "ガソリンカード",
    "ローン返済",
    "ローン借入",
)


def aggregate_balances(
    items: Iterable[dict],
    exclude_lctg: Iterable[str] = DEFAULT_EXCLUDE_LCTG,
    exclude_mctg: Iterable[str] = DEFAULT_EXCLUDE_MCTG,
    include_accounts: Iterable[str] = (),
) -> dict:
    """トランザクションを大項目/中項目別に集計する.

    Parameters
    ----------
    items : Iterable[dict]
        ``MoneyforwardTransactionItem`` の dict 表現。
    exclude_lctg : Iterable[str]
        集計から除外する大項目。
    exclude_mctg : Iterable[str]
        集計から除外する中項目。
    include_accounts : Iterable[str]
        ``transaction_account`` がここに含まれるレコードのみ集計する。
        空コレクションなら全口座対象。

    Returns
    -------
    dict
        ``{"lctg": {lctg: amount}, "mctg": {lctg: {mctg: amount}},
        "segment": {"収入合計": ..., "支出合計": ..., "収支合計": ...}}``。
    """
    exclude_lctg_set = set(exclude_lctg)
    exclude_mctg_set = set(exclude_mctg)
    include_accounts_set = set(include_accounts)

    lctg_totals: dict[str, int] = {}
    mctg_totals: dict[str, dict[str, int]] = {}
    segment = {"収入合計": 0, "支出合計": 0, "収支合計": 0}

    for item in items:
        account = item.get("transaction_account", "")
        if include_accounts_set and account not in include_accounts_set:
            continue

        lctg = item.get("lctg", "")
        mctg = item.get("mctg", "")
        if lctg in exclude_lctg_set:
            continue
        if mctg in exclude_mctg_set:
            continue

        amount_raw = item.get("amount_number", 0)
        try:
            amount = int(amount_raw)
        except (TypeError, ValueError):
            # JSONL から読むと文字列のことがあるので緩く扱う
            amount = int(str(amount_raw).replace(",", "") or 0)

        lctg_totals[lctg] = lctg_totals.get(lctg, 0) + amount
        mctg_totals.setdefault(lctg, {})
        mctg_totals[lctg][mctg] = mctg_totals[lctg].get(mctg, 0) + amount

        if amount > 0:
            segment["収入合計"] += amount
        else:
            segment["支出合計"] += amount
        segment["収支合計"] += amount

    return {"lctg": lctg_totals, "mctg": mctg_totals, "segment": segment}


def report_message(
    aggregated: dict, year: int, month: int, is_summary: bool = True
) -> str:
    """集計結果を元 PJ 互換の Slack テキスト形式に整形する.

    Parameters
    ----------
    aggregated : dict
        ``aggregate_balances`` の戻り値。
    year, month : int
        対象年月 (見出し用)。
    is_summary : bool
        True ならサマリのみ。False で大項目/中項目内訳を追記。

    Returns
    -------
    str
        改行を含む Slack 投稿向けテキスト。
    """
    segment = aggregated["segment"]
    lctg_totals = aggregated["lctg"]
    mctg_totals = aggregated["mctg"]

    lines: list[str] = []
    lines.append(f"{'総計':*^10} ({year}/{month})")
    lines.append(f"収入合計: {segment['収入合計']:,}円")
    lines.append(f"支出合計: {segment['支出合計']:,}円")

    lines.append(f"{'収支内訳':*^10} ({year}/{month})")
    for lctg, sub_value in lctg_totals.items():
        # 収入なら収入合計、支出なら支出合計を分母に取って割合算出
        denom = segment["収入合計"] if sub_value > 0 else segment["支出合計"]
        if denom != 0:
            percent: int | str = int((sub_value / denom) * 100)
        else:
            percent = "---"
        lines.append(f"{lctg}: {sub_value:,}円 ({percent}%)")

    if not is_summary:
        lines.append(f"{'収支詳細':*^10} ({year}/{month})")
        for lctg, sub_value in lctg_totals.items():
            lines.append(f"{lctg}: {sub_value:,}円")
            for mctg, mvalue in mctg_totals.get(lctg, {}).items():
                lines.append(f"  {mctg}: {mvalue:,}円")

    return "\n".join(lines) + "\n"


def report_csv(aggregated_by_month: dict[int, dict], year: int) -> str:
    """月次集計を 1 年分 CSV 化する (元 PJ ``report_csv`` 相当).

    Parameters
    ----------
    aggregated_by_month : dict[int, dict]
        ``{month: aggregate_balances() の戻り値}``。1〜12 月のうち存在する分。
    year : int
        対象年。

    Returns
    -------
    str
        ``utf_8_sig`` BOM 付きで保存される想定の CSV テキスト。
        ヘッダ行 = ["分類", "期間合計", "{year}年1月", ..., "{year}年12月"]。
    """
    months = list(range(1, 13))
    header = ["分類", "期間合計"] + [f"{year}年{m}月" for m in months]

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")

    def _segment_value(month: int, key: str) -> int:
        agg = aggregated_by_month.get(month)
        if not agg:
            return 0
        return int(agg["segment"].get(key, 0))

    def _lctg_value(month: int, lctg: str) -> int:
        agg = aggregated_by_month.get(month)
        if not agg:
            return 0
        return int(agg["lctg"].get(lctg, 0))

    def _mctg_value(month: int, lctg: str, mctg: str) -> int:
        agg = aggregated_by_month.get(month)
        if not agg:
            return 0
        return int(agg["mctg"].get(lctg, {}).get(mctg, 0))

    # 収支合計 / 収入合計 / 支出合計
    writer.writerow(header)
    for segment_key in ("収支合計", "収入合計", "支出合計"):
        total = sum(_segment_value(m, segment_key) for m in months)
        row: list[str | int] = [segment_key, total]
        row.extend(_segment_value(m, segment_key) for m in months)
        writer.writerow(row)

    # 収支内訳 (大項目)
    writer.writerow(header)
    all_lctg: list[str] = []
    seen_lctg: set[str] = set()
    for agg in aggregated_by_month.values():
        for lctg in agg["lctg"].keys():
            if lctg not in seen_lctg:
                seen_lctg.add(lctg)
                all_lctg.append(lctg)
    for lctg in all_lctg:
        total = sum(_lctg_value(m, lctg) for m in months)
        row = [lctg, total]
        row.extend(_lctg_value(m, lctg) for m in months)
        writer.writerow(row)

    # 収支詳細 (大項目/中項目)
    writer.writerow(header)
    for lctg in all_lctg:
        seen_mctg: set[str] = set()
        all_mctg: list[str] = []
        for agg in aggregated_by_month.values():
            for mctg in agg["mctg"].get(lctg, {}).keys():
                if mctg not in seen_mctg:
                    seen_mctg.add(mctg)
                    all_mctg.append(mctg)
        for mctg in all_mctg:
            total = sum(_mctg_value(m, lctg, mctg) for m in months)
            row = [f"{lctg}/{mctg}", total]
            row.extend(_mctg_value(m, lctg, mctg) for m in months)
            writer.writerow(row)

    return out.getvalue()
