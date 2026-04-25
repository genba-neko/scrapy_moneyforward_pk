"""reports.asset_allocation 単体テスト。"""

from __future__ import annotations

from pathlib import Path

from moneyforward_pk.reports import asset_allocation as aa_mod
from moneyforward_pk.reports._loader import filter_year_month_day, iter_jsonl

FIXTURE = (
    Path(__file__).parent / "fixtures" / "reports" / "sample_asset_allocation.jsonl"
)


def _load() -> list[dict]:
    return list(iter_jsonl(FIXTURE))


def test_aggregate_classifies_known_asset_types():
    items = list(filter_year_month_day(_load(), 2026, 4, 25))
    agg = aa_mod.aggregate_asset_allocation(items)
    assert agg["total"] == 100000 + 500000 + 200000 + 300000 + 400000
    assert agg["classes"]["生活費"] == 100000  # mf_asset_allocation-service@cash1
    assert agg["classes"]["待機資金"] == 200000  # 静岡銀行 portfolio_det_depo
    assert agg["classes"]["株式（長期）"] == 500000
    assert agg["classes"]["投資信託"] == 300000
    assert agg["classes"]["債券"] == 400000
    assert agg["unknown"] == []


def test_aggregate_unknown_collected():
    items = [{"asset_type": "weird", "asset_item_key": "abc", "amount_value": 99}]
    agg = aa_mod.aggregate_asset_allocation(items)
    assert agg["total"] == 99
    assert len(agg["unknown"]) == 1
    assert agg["unknown"][0]["asset_type"] == "weird"


def test_filter_year_month_day_excludes_other_dates():
    rows = list(filter_year_month_day(_load(), 2026, 4, 24))
    assert len(rows) == 1
    assert rows[0]["asset_name"] == "前日分"


def test_classify_shiz_stock_goes_to_standby():
    item = {
        "asset_type": "portfolio_det_eq",
        "asset_item_key": "xmf_shiz_asset_allocation-service@s1",
        "asset_name": "静岡株式XYZ",
        "amount_value": 1000,
    }
    agg = aa_mod.aggregate_asset_allocation([item])
    assert agg["classes"]["待機資金"] == 1000


def test_report_message_format():
    items = list(filter_year_month_day(_load(), 2026, 4, 25))
    agg = aa_mod.aggregate_asset_allocation(items)
    msg = aa_mod.report_message(agg, 2026, 4, 25)
    assert "アセットアロケーション" in msg
    assert "(2026/4/25)" in msg
    assert "総資産額=1,500,000円" in msg
    assert "生活費=100,000円" in msg
    assert "株式（長期）=500,000円" in msg


def test_report_message_zero_total_no_zerodiv():
    agg = aa_mod.aggregate_asset_allocation([])
    msg = aa_mod.report_message(agg, 2026, 4, 25)
    assert "総資産額=0円" in msg
    assert "(---%)" in msg  # 全クラスが --- 表示
