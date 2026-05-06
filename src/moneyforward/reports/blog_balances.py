"""ブログ向け収支 Markdown 生成 (Google Charts 埋め込み).

元 PJ ``get_balances_blog.py`` の純関数移植。
DynamoDB 依存を除去し、aggregate_balances() の戻り値を入力とする。
口座種別分類は ``config/account_types.yaml`` に外部化。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import yaml

from moneyforward.reports._loader import filter_year_month
from moneyforward.reports.balances import aggregate_balances

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# lctg 分類定数
# ---------------------------------------------------------------------------
LCTG_LIFE: tuple[str, ...] = (
    "住宅",
    "食費",
    "水道・光熱費",
    "通信費",
    "交通費",
    "自動車",
    "衣服・美容",
    "健康・医療",
    "教養・教育",
    "日用品",
)
LCTG_LIFE_VARIABLE: tuple[str, ...] = (
    "食費",
    "交通費",
    "自動車",
    "衣服・美容",
    "健康・医療",
    "日用品",
    "その他",
)
LCTG_LIFE_FIXED: tuple[str, ...] = (
    "住宅",
    "水道・光熱費",
    "通信費",
    "教養・教育",
    "保険",
)

EXCLUDE_LCTG: tuple[str, ...] = ("現金・カード", "税・社会保障")
EXCLUDE_MCTG: tuple[str, ...] = (
    "給与",
    "還付金",
    "ガソリンカード",
    "相続",
    "その他交際費",
    "ローン借入",
    "ローン返済",
)
EXCLUDE_MCTG_LIFE: tuple[str, ...] = EXCLUDE_MCTG + ("配当所得",)

DISPLAY_ITEMS_LIFE: tuple[str, ...] = LCTG_LIFE
DISPLAY_ITEMS_PLAY: tuple[str, ...] = (
    "映画・音楽",
    "ゲーム",
    "漫画・小説",
    "模型・プラモデル",
    "コレクション",
    "アウトドア",
    "美術館・博物館",
    "スポーツ",
    "旅行",
)
DISPLAY_ITEMS_SPEC: tuple[str, ...] = (
    "PC・ガジェット",
    "工具・資材",
    "家具・家電",
    "バイク",
    "自転車",
    "カメラ",
    "矯正歯科",
)
DISPLAY_ITEMS_RECEIPT: tuple[str, ...] = (
    "株主優待券",
    "共通ギフト券",
    "クーポン利用",
    "ポイント利用",
    "キャッシュバック",
    "売上金",
    "配当所得",
)
DISPLAY_ITEMS_PAYMENT: tuple[str, ...] = LCTG_LIFE + ("趣味・娯楽", "特別な支出")

ACCOUNT_TYPE_KEYS: tuple[str, ...] = ("wallet", "prepaid", "mall", "creditcard", "bank")


# ---------------------------------------------------------------------------
# YAML 読み込み
# ---------------------------------------------------------------------------


def load_account_types(path: Path) -> dict[str, list[str]] | None:
    """``config/account_types.yaml`` を読み込む。不在時は警告のみ ``None`` を返す.

    Returns
    -------
    dict | None
        ``{"wallet": [...], "prepaid": [...], "mall": [...], "creditcard": [...], "bank": [...]}``
        ファイル不在時は ``None`` (口座種別分析スキップの合図)。
    """
    if not path.exists():
        logger.warning(
            "口座種別分類ファイルが見つかりません: %s "
            "(example をコピーして作成: "
            "copy config/account_types.example.yaml config/account_types.yaml)",
            path,
        )
        return None

    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return {k: [] for k in ACCOUNT_TYPE_KEYS}

    result: dict[str, list[str]] = {}
    for key in ACCOUNT_TYPE_KEYS:
        entries = raw.get(key) or []
        if not isinstance(entries, list):
            raise ValueError(f"account_types YAML: '{key}' must be a list")
        result[key] = [str(e) for e in entries]
    return result


# ---------------------------------------------------------------------------
# 純関数: Google Charts Markdown 生成
# ---------------------------------------------------------------------------


def report_payment_for_google_chart(
    aggregated: dict,
    display_items: Iterable[str],
    year: int,
    month: int | None = None,
    display_lctg: str | None = None,
) -> str:
    """支出 Google Charts PieChart Markdown を生成する.

    Parameters
    ----------
    aggregated:
        ``aggregate_balances()`` の戻り値。
    display_items:
        表示する lctg 名 (``display_lctg=None``) または mctg 名のリスト。
    year, month:
        対象年月。``month=None`` で年間集計。
    display_lctg:
        指定時は当該 lctg の mctg レベルで集計。``None`` なら lctg レベル。

    Returns
    -------
    str
        Hexo/WordPress 向け Google Charts 埋め込み Markdown。
    """
    display_items_list = list(display_items)
    segment = aggregated["segment"]
    lctg_totals: dict[str, int] = aggregated["lctg"]
    mctg_totals: dict[str, dict[str, int]] = aggregated["mctg"]

    total_payment = -segment["支出合計"]
    period_str = f"{year}年{month}月" if month is not None else f"{year}年"

    lines: list[str] = []
    lines.append("{% alert warning %}")
    lines.append(f"{period_str}の支出は**{total_payment:,}円**でした")
    lines.append("{% endalert %}")
    lines.append("")

    if display_lctg is not None and not mctg_totals.get(display_lctg):
        lines.append(f"{display_lctg}による支出はありませんでした")
        return "\n".join(lines) + "\n"

    lines.append("{% googlecharts PieChart 100% %}")
    lines.append(f"{period_str}支出合計: {total_payment:,}円")
    lines.append("{}")
    lines.append("'支出項目','支出額（円）'")

    specified = set(display_items_list)

    if display_lctg is None:
        for item in display_items_list:
            val = lctg_totals.get(item, 0)
            lines.append(f"'{item}', {-val if val < 0 else 0}")
        other = sum(
            -v for lctg, v in lctg_totals.items() if lctg not in specified and v < 0
        )
        lines.append(f"'その他', {other}")
    else:
        mctg_data = mctg_totals.get(display_lctg, {})
        for item in display_items_list:
            val = mctg_data.get(item, 0)
            lines.append(f"'{item}', {-val if val < 0 else 0}")
        other = sum(
            -v for mctg, v in mctg_data.items() if mctg not in specified and v < 0
        )
        lines.append(f"'その他', {other}")

    lines.append("{% endgooglecharts %}")
    return "\n".join(lines) + "\n"


def report_receipt_for_google_chart(
    aggregated: dict,
    display_items: Iterable[str],
    year: int,
    month: int | None = None,
) -> str:
    """収入 Google Charts PieChart Markdown を生成する.

    Parameters
    ----------
    aggregated:
        ``aggregate_balances()`` の戻り値。lctg="収入" の mctg が集計対象。
    display_items:
        表示する mctg 名のリスト (lctg="収入" 配下)。
    year, month:
        対象年月。``month=None`` で年間集計。

    Returns
    -------
    str
        Hexo/WordPress 向け Google Charts 埋め込み Markdown。
    """
    display_items_list = list(display_items)
    segment = aggregated["segment"]
    mctg_totals: dict[str, dict[str, int]] = aggregated["mctg"]

    total_receipt = segment["収入合計"]
    period_str = f"{year}年{month}月" if month is not None else f"{year}年"

    mctg_data = mctg_totals.get("収入", {})
    specified = set(display_items_list)

    lines: list[str] = []
    lines.append("{% alert success %}")
    lines.append(f"{period_str}の収入は**{total_receipt:,}円**でした")
    lines.append("{% endalert %}")
    lines.append("")
    lines.append("{% googlecharts PieChart 100% %}")
    lines.append(f"{period_str}収入合計: {total_receipt:,}円")
    lines.append("{}")
    lines.append("'収入項目','収入額（円）'")
    for item in display_items_list:
        lines.append(f"'{item}', {mctg_data.get(item, 0)}")
    other = sum(v for mctg, v in mctg_data.items() if mctg not in specified and v > 0)
    lines.append(f"'その他', {other}")
    lines.append("{% endgooglecharts %}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 高レベル: 月次ブログレポート全体
# ---------------------------------------------------------------------------


def report_blog_balances(
    items: list[dict],
    year: int,
    month: int,
    account_types: dict[str, list[str]] | None = None,
) -> str:
    """月次ブログ収支レポート全体を生成する.

    Parameters
    ----------
    items:
        当月の ``MoneyforwardTransactionItem`` dict リスト。
    year, month:
        対象年月。
    account_types:
        ``load_account_types()`` の戻り値。``None`` なら口座種別分析をスキップ。

    Returns
    -------
    str
        Google Charts 埋め込み Markdown。
    """
    message = ""

    # 1. 口座種別分析
    if account_types:
        message += _report_payment_by_account_type(items, year, month, account_types)

    # 2. 生活費内訳
    _exclude_lctg_life = list(EXCLUDE_LCTG) + [
        "趣味・娯楽",
        "特別な支出",
        "交際費",
        "保険",
        "その他",
    ]
    agg_life = aggregate_balances(
        items, exclude_lctg=_exclude_lctg_life, exclude_mctg=list(EXCLUDE_MCTG)
    )
    message += "### 実支出内訳（生活費）\n\n"
    message += "生活費の月間支出額の内訳です。\n\n"
    message += report_payment_for_google_chart(
        agg_life, DISPLAY_ITEMS_LIFE, year, month
    )
    message += "\n"

    # 3. 趣味・娯楽内訳
    _exclude_lctg_play = (
        list(EXCLUDE_LCTG)
        + list(LCTG_LIFE)
        + ["特別な支出", "交際費", "保険", "その他"]
    )
    agg_play = aggregate_balances(
        items, exclude_lctg=_exclude_lctg_play, exclude_mctg=list(EXCLUDE_MCTG)
    )
    message += "### 実支出内訳（趣味・娯楽）\n\n"
    message += "生活費以外の月間支出のうち**趣味・娯楽**の内訳です。\n\n"
    message += report_payment_for_google_chart(
        agg_play, DISPLAY_ITEMS_PLAY, year, month, "趣味・娯楽"
    )
    message += "\n"

    # 4. 特別な支出内訳
    _exclude_lctg_spec = (
        list(EXCLUDE_LCTG)
        + list(LCTG_LIFE)
        + ["趣味・娯楽", "交際費", "保険", "その他"]
    )
    agg_spec = aggregate_balances(
        items, exclude_lctg=_exclude_lctg_spec, exclude_mctg=list(EXCLUDE_MCTG)
    )
    message += "### 実支出内訳（特別な支出）\n\n"
    message += "生活費以外の月間支出のうち**特別な支出**の内訳です。\n\n"
    message += report_payment_for_google_chart(
        agg_spec, DISPLAY_ITEMS_SPEC, year, month, "特別な支出"
    )
    message += "\n"

    # 5. 総収支
    message += "## 総収支分析\n\n"
    agg_all = aggregate_balances(
        items, exclude_lctg=list(EXCLUDE_LCTG), exclude_mctg=list(EXCLUDE_MCTG)
    )
    message += "### 総収入\n\n"
    message += (
        "獲得したポイントや優待券・割引券による割引額を収入として集計した内訳です。\n\n"
    )
    message += report_receipt_for_google_chart(
        agg_all, DISPLAY_ITEMS_RECEIPT, year, month
    )
    message += "\n"
    message += "### 総支出\n\n"
    message += "ポイントや割引を含むすべての支出の内訳です。\n\n"
    message += report_payment_for_google_chart(
        agg_all, DISPLAY_ITEMS_PAYMENT, year, month
    )
    message += "\n"

    return message


def report_cost_of_living(items: list[dict], year: int, month: int) -> str:
    """生活費収支分析（変動費/固定費）Markdown テーブルを生成する.

    各月の変動費・固定費・特別費・収支を表形式で出力する。

    Parameters
    ----------
    items:
        ``year`` の全 transaction レコード。``filter_year_month`` で月次抽出する。
    year, month:
        対象年と最終集計月 (1〜month の各月を出力)。

    Returns
    -------
    str
        Markdown テーブル (3 テーブル: 全体/変動費/固定費)。
    """
    message = ""

    # --- 全体サマリテーブル ---
    message += "| 集計期間 | 収入 | 変動費 | 固定費 | 特別費 | 収支 |\n"
    message += "| --- | --: | --: | --: | --: | --: |\n"

    totals = {"receipt": 0, "variable": 0, "fixed": 0, "others": 0}
    for mon in range(1, month + 1):
        row = _compute_cost_row(items, year, mon)
        totals["receipt"] += row["receipt"]
        totals["variable"] += row["variable"]
        totals["fixed"] += row["fixed"]
        totals["others"] += row["others"]
        balance = row["receipt"] - row["variable"] - row["fixed"] - row["others"]
        message += (
            f"| {year}年{mon}月 | {row['receipt']:,}円 "
            f"| {row['variable']:,}円 | {row['fixed']:,}円 "
            f"| {row['others']:,}円 | {balance:,}円 |\n"
        )

    annual_balance = (
        totals["receipt"] - totals["variable"] - totals["fixed"] - totals["others"]
    )
    message += (
        f"| {year}年累計 | {totals['receipt']:,}円 "
        f"| {totals['variable']:,}円 | {totals['fixed']:,}円 "
        f"| {totals['others']:,}円 | {annual_balance:,}円 |\n"
    )
    message += "\n"

    # --- 変動費テーブル ---
    message += "| 集計期間 | 変動費収入 | 変動費支出 | 変動費収支 |\n"
    message += "| --- | --: | --: | --: |\n"
    total_var_receipt = 0
    total_var_payment = 0
    for mon in range(1, month + 1):
        monthly = list(filter_year_month(items, year, mon))
        _exclude_var = list(EXCLUDE_LCTG) + ["趣味・娯楽", "特別な支出"]
        agg = aggregate_balances(
            monthly, exclude_lctg=_exclude_var, exclude_mctg=list(EXCLUDE_MCTG_LIFE)
        )
        r = agg["segment"]["収入合計"]
        p = -agg["segment"]["支出合計"]
        total_var_receipt += r
        total_var_payment += p
        message += f"| {year}年{mon}月 | {r:,}円 | {p:,}円 | {r - p:,}円 |\n"
    message += (
        f"| {year}年累計 | {total_var_receipt:,}円 "
        f"| {total_var_payment:,}円 | {total_var_receipt - total_var_payment:,}円 |\n"
    )
    message += "\n"

    # --- 固定費テーブル ---
    message += "| 集計期間 | 固定費支出 |\n"
    message += "| --- | --: |\n"
    total_fixed_payment = 0
    for mon in range(1, month + 1):
        monthly = list(filter_year_month(items, year, mon))
        _exclude_fixed = (
            list(EXCLUDE_LCTG) + ["趣味・娯楽", "特別な支出"] + list(LCTG_LIFE_VARIABLE)
        )
        agg = aggregate_balances(
            monthly, exclude_lctg=_exclude_fixed, exclude_mctg=list(EXCLUDE_MCTG)
        )
        p = -agg["segment"]["支出合計"]
        total_fixed_payment += p
        message += f"| {year}年{mon}月 | {p:,}円 |\n"
    message += f"| {year}年累計 | {total_fixed_payment:,}円 |\n"

    return message


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _compute_cost_row(items: list[dict], year: int, month: int) -> dict[str, int]:
    """1 か月分の収入/変動費/固定費/特別費を集計して返す."""
    monthly = list(filter_year_month(items, year, month))

    # 収入
    agg = aggregate_balances(
        monthly, exclude_lctg=list(EXCLUDE_LCTG), exclude_mctg=list(EXCLUDE_MCTG_LIFE)
    )
    receipt = agg["segment"]["収入合計"]

    # 変動費
    _exclude_var = (
        list(EXCLUDE_LCTG) + ["趣味・娯楽", "特別な支出"] + list(LCTG_LIFE_FIXED)
    )
    agg = aggregate_balances(
        monthly, exclude_lctg=_exclude_var, exclude_mctg=list(EXCLUDE_MCTG_LIFE)
    )
    variable = -agg["segment"]["支出合計"]

    # 固定費
    _exclude_fixed = (
        list(EXCLUDE_LCTG) + ["趣味・娯楽", "特別な支出"] + list(LCTG_LIFE_VARIABLE)
    )
    agg = aggregate_balances(
        monthly, exclude_lctg=_exclude_fixed, exclude_mctg=list(EXCLUDE_MCTG)
    )
    fixed = -agg["segment"]["支出合計"]

    # 特別費（生活費以外合計）
    _exclude_others = (
        list(EXCLUDE_LCTG) + list(LCTG_LIFE) + ["交際費", "保険", "その他"]
    )
    agg = aggregate_balances(
        monthly, exclude_lctg=_exclude_others, exclude_mctg=list(EXCLUDE_MCTG)
    )
    others = -agg["segment"]["支出合計"]

    return {"receipt": receipt, "variable": variable, "fixed": fixed, "others": others}


def _report_payment_by_account_type(
    items: list[dict],
    year: int,
    month: int,
    account_types: dict[str, list[str]],
) -> str:
    """支払方法別の分析テーブルを生成する."""
    exc_lctg = list(EXCLUDE_LCTG)
    exc_mctg = list(EXCLUDE_MCTG)

    def _payment(
        include_accounts: list[str], exclude_lctg: list[str] | None = None
    ) -> int:
        agg = aggregate_balances(
            items,
            exclude_lctg=exclude_lctg if exclude_lctg is not None else exc_lctg,
            exclude_mctg=exc_mctg,
            include_accounts=include_accounts,
        )
        return -agg["segment"]["支出合計"]

    lines: list[str] = [
        "### 支払方法別の分析",
        "",
        "支払方法別の支出額です。",
        "",
        "| 支払分類 | 金額 | 備考 |",
        "| --- | --: | --- |",
    ]

    wallet = account_types.get("wallet", [])
    lines.append(f"| 現金 | **{_payment(wallet):,}円** |  |")

    prepaid = account_types.get("prepaid", [])
    lines.append(f"| 電子マネー | **{_payment(prepaid):,}円** |  |")

    mall = account_types.get("mall", [])
    lines.append(
        f"| 主要ショッピングサイト | **{_payment(mall):,}円** | Amazon、楽天 |"
    )

    creditcard = account_types.get("creditcard", [])
    cc_all = _payment(creditcard, exclude_lctg=[])
    cc = _payment(creditcard)
    lines.append(
        f"| クレジットカード | **{cc:,}円** | 電子マネーチャージ含むと**{cc_all:,}円** |"
    )

    bank = account_types.get("bank", [])
    lines.append(f"| 銀行振込 | **{_payment(bank):,}円** |  |")

    lines.append("")
    return "\n".join(lines) + "\n"
