"""reports.blog_asset_allocation 単体テスト。"""

from __future__ import annotations

from pathlib import Path

from moneyforward.reports._loader import iter_jsonl
from moneyforward.reports.asset_allocation import (
    ASSET_CLASSES,
    aggregate_asset_allocation,
)
from moneyforward.reports.blog_asset_allocation import (
    report_asset_allocation_pie_chart,
    report_blog_asset_allocation,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "reports" / "sample_asset_allocation.jsonl"
)


def _items() -> list[dict]:
    return list(iter_jsonl(FIXTURE))


def _agg_current() -> dict:
    from moneyforward.reports._loader import filter_year_month_day

    daily = list(filter_year_month_day(_items(), 2026, 4, 25))
    return aggregate_asset_allocation(daily)


# ---------------------------------------------------------------------------
# report_asset_allocation_pie_chart
# ---------------------------------------------------------------------------


def test_pie_chart_contains_all_asset_classes():
    agg = _agg_current()
    result = report_asset_allocation_pie_chart(agg, 2026, 4, 25)
    assert "{% googlecharts PieChart 100% %}" in result
    assert "{% endgooglecharts %}" in result
    assert "2026年4月25日 資産合計:" in result
    for name in ASSET_CLASSES:
        assert f"'{name}'" in result


def test_pie_chart_total_amount():
    agg = _agg_current()
    result = report_asset_allocation_pie_chart(agg, 2026, 4, 25)
    total = agg["total"]
    assert f"{total:,}円" in result


# ---------------------------------------------------------------------------
# report_blog_asset_allocation
# ---------------------------------------------------------------------------


def test_blog_asset_allocation_no_data_returns_message():
    result = report_blog_asset_allocation(_items(), 2026, 12, 31)
    assert "データがありません" in result


def test_blog_asset_allocation_includes_pie_and_column():
    result = report_blog_asset_allocation(_items(), 2026, 4, 25)
    assert "{% googlecharts PieChart 100% %}" in result
    assert "{% googlecharts ColumnChart 100% %}" in result
    assert "isStacked" in result
    assert "2026年4月" in result


def test_blog_asset_allocation_alert_jan_only():
    result = report_blog_asset_allocation(_items(), 2026, 4, 25)
    assert "{% alert success %}" in result


def test_blog_asset_allocation_column_chart_has_header():
    result = report_blog_asset_allocation(_items(), 2026, 4, 25)
    assert "'年月'" in result
    for name in ASSET_CLASSES:
        assert f"'{name}'" in result
