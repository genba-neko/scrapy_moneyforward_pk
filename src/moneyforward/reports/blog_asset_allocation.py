"""ブログ向け資産配分 Markdown 生成 (Google Charts 埋め込み).

元 PJ ``get_asset_allocation_blog.py`` の純関数移植。
DynamoDB 依存を除去し、aggregate_asset_allocation() の戻り値を入力とする。
"""

from __future__ import annotations

import logging
from datetime import date

from moneyforward.reports._loader import filter_year_month_day
from moneyforward.reports.asset_allocation import (
    ASSET_CLASSES,
    aggregate_asset_allocation,
)
from moneyforward.reports.segregated_asset import apply_adjustments, compute_adjustments

logger = logging.getLogger(__name__)


def report_asset_allocation_pie_chart(
    aggregated: dict,
    year: int,
    month: int,
    day: int,
) -> str:
    """資産配分 Google Charts PieChart Markdown を生成する.

    Parameters
    ----------
    aggregated:
        ``aggregate_asset_allocation()`` (＋分別管理調整済み) の戻り値。
    year, month, day:
        対象日付 (見出し用)。

    Returns
    -------
    str
        Hexo/WordPress 向け Google Charts 埋め込み Markdown。
    """
    total = aggregated["total"]
    classes: dict[str, int] = aggregated["classes"]

    lines: list[str] = []
    lines.append("{% alert success %}")
    lines.append(f"{year}年{month}月{day}日の資産額は**{total:,}円**でした")
    lines.append("{% endalert %}")
    lines.append("")
    lines.append("{% googlecharts PieChart 100% %}")
    lines.append(f"{year}年{month}月{day}日 資産合計: {total:,}円")
    lines.append("{}")
    lines.append("'資産クラス','資産額（円）'")
    for name in ASSET_CLASSES:
        lines.append(f"'{name}', {classes.get(name, 0)}")
    lines.append("{% endgooglecharts %}")
    return "\n".join(lines) + "\n"


def report_blog_asset_allocation(
    items: list[dict],
    year: int,
    month: int,
    day: int,
    segregated_config: dict | None = None,
) -> str:
    """月次ブログ資産配分レポート全体を生成する.

    円グラフ（当月）＋縦棒グラフ（年初比・前月比推移）を出力する。

    Parameters
    ----------
    items:
        ``moneyforward_asset_allocation.json`` 全レコード。
    year, month, day:
        対象日付。
    segregated_config:
        ``load_segregated_config()`` の戻り値。``None`` で調整なし。

    Returns
    -------
    str
        Google Charts 埋め込み Markdown。
    """

    def _aggregate(y: int, m: int, d: int) -> dict | None:
        daily = list(filter_year_month_day(items, y, m, d))
        if not daily:
            return None
        agg = aggregate_asset_allocation(daily)
        if segregated_config:
            adj = compute_adjustments(segregated_config, date(y, m, d))
            agg = apply_adjustments(agg, adj)
        return agg

    # 当月
    agg_now = _aggregate(year, month, day)
    if agg_now is None:
        return f"{year}年{month}月{day}日のデータがありません\n"

    message = ""
    message += report_asset_allocation_pie_chart(agg_now, year, month, day)
    message += "\n"

    # 年初
    agg_jan = _aggregate(year, 1, day)
    jan_available = agg_jan is not None
    total_begin = agg_jan["total"] if jan_available else None

    # 前月
    total_prev: int | None = None
    if month > 1:
        agg_prev = _aggregate(year, month - 1, day)
        if agg_prev:
            total_prev = agg_prev["total"]

    total_now = agg_now["total"]
    ytd: int | None = (total_now - total_begin) if total_begin is not None else None

    # 前月比・年初比アラート
    mom_str = f"{total_now - total_prev:+,}円" if total_prev is not None else "―円"
    ytd_str = f"{ytd:+,}円" if ytd is not None else "―円（年初データなし）"
    message += "{% alert success %}\n"
    message += f"**前月比{mom_str}、年初比{ytd_str}**\n"
    message += "{% endalert %}\n"
    message += "\n"

    # ColumnChart: 1月〜当月の推移
    ytd_label = f"{ytd:+,}円" if ytd is not None else "―円"
    message += "{% googlecharts ColumnChart 100% %}\n"
    message += f"{year}年資産推移（年初比：{ytd_label}）\n"
    message += '{"isStacked": true}\n'

    # ヘッダ行
    header = "'年月'," + ",".join(f"'{name}'" for name in ASSET_CLASSES)
    message += header + "\n"

    for mon in range(1, month + 1):
        agg_mon = _aggregate(year, mon, day)
        if agg_mon is None:
            continue
        classes = agg_mon["classes"]
        vals = ",".join(str(classes.get(name, 0)) for name in ASSET_CLASSES)
        message += f"'{year}年{mon}月',{vals}\n"

    message += "{% endgooglecharts %}\n"
    return message
