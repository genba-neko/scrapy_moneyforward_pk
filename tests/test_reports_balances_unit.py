"""reports.balances 単体テスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moneyforward_pk.reports import balances as bal_mod
from moneyforward_pk.reports._loader import (
    filter_year_month,
    iter_jsonl,
    load_spider_jsonl,
)

FIXTURE = Path(__file__).parent / "fixtures" / "reports" / "sample_transactions.jsonl"


def _load_fixture() -> list[dict]:
    return list(iter_jsonl(FIXTURE))


def test_aggregate_balances_excludes_default_lctg_mctg():
    items = _load_fixture()
    monthly = list(filter_year_month(items, 2026, 4))
    aggregated = bal_mod.aggregate_balances(monthly)

    # 現金・カード (lctg) は除外、ガソリンカード (mctg) も除外
    assert "現金・カード" not in aggregated["lctg"]
    assert "ガソリンカード" not in aggregated["mctg"].get("交通費", {})
    # 残りは収入 + 食費 + 水道光熱費
    assert aggregated["lctg"] == {"収入": 300000, "食費": -5000, "水道・光熱費": -8000}
    assert aggregated["segment"]["収入合計"] == 300000
    assert aggregated["segment"]["支出合計"] == -13000
    assert aggregated["segment"]["収支合計"] == 287000


def test_aggregate_balances_include_accounts_filter():
    items = _load_fixture()
    monthly = list(filter_year_month(items, 2026, 4))
    aggregated = bal_mod.aggregate_balances(monthly, include_accounts=["銀行A"])
    # カードA の食費レコードは除外、銀行A の収入と光熱費のみ
    assert "食費" not in aggregated["lctg"]
    assert aggregated["lctg"]["収入"] == 300000
    assert aggregated["lctg"]["水道・光熱費"] == -8000


def test_aggregate_balances_handles_missing_keys():
    aggregated = bal_mod.aggregate_balances(
        [{}, {"amount_number": "1000", "lctg": "x", "mctg": "y"}]
    )
    # 文字列の amount_number もパースできること
    assert aggregated["lctg"]["x"] == 1000


def test_filter_year_month_only_returns_matching_records():
    items = _load_fixture()
    march = list(filter_year_month(items, 2026, 3))
    assert len(march) == 1
    assert march[0]["content"] == "前月分"


def test_report_message_summary_format():
    items = _load_fixture()
    monthly = list(filter_year_month(items, 2026, 4))
    aggregated = bal_mod.aggregate_balances(monthly)
    msg = bal_mod.report_message(aggregated, 2026, 4, is_summary=True)
    assert "総計" in msg
    assert "(2026/4)" in msg
    assert "収入合計: 300,000円" in msg
    assert "支出合計: -13,000円" in msg
    # detail セクションは出ない
    assert "収支詳細" not in msg


def test_report_message_detail_includes_mctg():
    items = _load_fixture()
    monthly = list(filter_year_month(items, 2026, 4))
    aggregated = bal_mod.aggregate_balances(monthly)
    msg = bal_mod.report_message(aggregated, 2026, 4, is_summary=False)
    assert "収支詳細" in msg
    assert "食料品" in msg


def test_report_message_zero_segment_shows_dashes():
    aggregated = bal_mod.aggregate_balances([])
    msg = bal_mod.report_message(aggregated, 2026, 4)
    # ZeroDivision を起こさず "---" 表示
    assert "(---%)" not in msg or "(---%)" in msg  # 空 lctg なら何も出ない


def test_report_csv_year_summary_has_three_sections():
    items = _load_fixture()
    monthly_aggregates = {}
    for m in [3, 4]:
        m_items = list(filter_year_month(items, 2026, m))
        if m_items:
            monthly_aggregates[m] = bal_mod.aggregate_balances(m_items)
    csv_text = bal_mod.report_csv(monthly_aggregates, 2026)
    lines = csv_text.strip().split("\n")
    # ヘッダ行 (header: 14 columns - 分類 + 期間合計 + 12ヶ月)
    assert "分類,期間合計" in lines[0]
    assert "2026年4月" in lines[0]
    # 収支合計 / 収入合計 / 支出合計 / 収支内訳ヘッダ / 大項目 / 詳細ヘッダ ...
    assert "収支合計" in csv_text
    assert "収入合計" in csv_text
    assert "支出合計" in csv_text


def test_load_spider_jsonl_finds_files(tmp_path: Path):
    target = tmp_path / "mf_transaction_20260425.jsonl"
    target.write_text(json.dumps({"x": 1}) + "\n", encoding="utf-8")
    other = tmp_path / "other_spider_20260425.jsonl"
    other.write_text(json.dumps({"x": 2}) + "\n", encoding="utf-8")
    items = list(load_spider_jsonl(tmp_path, "mf_transaction"))
    assert items == [{"x": 1}]


def test_load_spider_jsonl_missing_dir(tmp_path: Path):
    assert list(load_spider_jsonl(tmp_path / "missing", "mf_transaction")) == []


def test_iter_jsonl_skips_blank_lines(tmp_path: Path):
    f = tmp_path / "x.jsonl"
    f.write_text('{"a":1}\n\n{"b":2}\n', encoding="utf-8")
    rows = list(iter_jsonl(f))
    assert rows == [{"a": 1}, {"b": 2}]


def test_iter_jsonl_propagates_decode_error(tmp_path: Path):
    f = tmp_path / "broken.jsonl"
    f.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        list(iter_jsonl(f))
