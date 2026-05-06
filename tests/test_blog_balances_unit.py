"""reports.blog_balances 単体テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from moneyforward.reports._loader import filter_year_month, iter_jsonl
from moneyforward.reports.blog_balances import (
    load_account_types,
    report_blog_balances,
    report_cost_of_living,
    report_payment_for_google_chart,
    report_receipt_for_google_chart,
)

FIXTURE = Path(__file__).parent / "fixtures" / "reports" / "sample_transactions.jsonl"


def _items() -> list[dict]:
    return list(iter_jsonl(FIXTURE))


def _agg(lctg: dict, mctg: dict, segment: dict) -> dict:
    return {"lctg": lctg, "mctg": mctg, "segment": segment}


# ---------------------------------------------------------------------------
# load_account_types
# ---------------------------------------------------------------------------


def test_load_account_types_missing_file_returns_none(tmp_path):
    result = load_account_types(tmp_path / "no_such.yaml")
    assert result is None


def test_load_account_types_valid_yaml(tmp_path):
    yaml_path = tmp_path / "account_types.yaml"
    yaml_path.write_text(
        "wallet:\n  - 現金\nprepaid:\n  - PayPay\nmall: []\ncreditcard: []\nbank: []\n",
        encoding="utf-8",
    )
    result = load_account_types(yaml_path)
    assert result is not None
    assert result["wallet"] == ["現金"]
    assert result["prepaid"] == ["PayPay"]
    assert result["mall"] == []


def test_load_account_types_invalid_list_raises(tmp_path):
    yaml_path = tmp_path / "account_types.yaml"
    yaml_path.write_text(
        "wallet: not_a_list\nprepaid: []\nmall: []\ncreditcard: []\nbank: []\n"
    )
    with pytest.raises(ValueError, match="must be a list"):
        load_account_types(yaml_path)


# ---------------------------------------------------------------------------
# report_payment_for_google_chart
# ---------------------------------------------------------------------------


def test_payment_chart_lctg_level_basic():
    agg = _agg(
        lctg={"食費": -5000, "水道・光熱費": -8000, "趣味・娯楽": -3000},
        mctg={},
        segment={"支出合計": -16000, "収入合計": 0, "収支合計": -16000},
    )
    result = report_payment_for_google_chart(agg, ["食費", "水道・光熱費"], 2026, 4)
    assert "{% googlecharts PieChart 100% %}" in result
    assert "2026年4月支出合計: 16,000円" in result
    assert "'食費', 5000" in result
    assert "'水道・光熱費', 8000" in result
    assert "'その他', 3000" in result
    assert "{% endgooglecharts %}" in result


def test_payment_chart_mctg_level():
    agg = _agg(
        lctg={"趣味・娯楽": -10000},
        mctg={"趣味・娯楽": {"ゲーム": -4000, "旅行": -5000, "その他趣味": -1000}},
        segment={"支出合計": -10000, "収入合計": 0, "収支合計": -10000},
    )
    result = report_payment_for_google_chart(
        agg, ["ゲーム", "旅行"], 2026, 4, "趣味・娯楽"
    )
    assert "'ゲーム', 4000" in result
    assert "'旅行', 5000" in result
    assert "'その他', 1000" in result


def test_payment_chart_empty_display_lctg():
    agg = _agg(
        lctg={}, mctg={}, segment={"支出合計": -5000, "収入合計": 0, "収支合計": -5000}
    )
    result = report_payment_for_google_chart(agg, [], 2026, 4, "趣味・娯楽")
    assert "趣味・娯楽による支出はありませんでした" in result
    assert "{% googlecharts" not in result


def test_payment_chart_year_mode():
    agg = _agg(
        lctg={"食費": -60000},
        mctg={},
        segment={"支出合計": -60000, "収入合計": 0, "収支合計": -60000},
    )
    result = report_payment_for_google_chart(agg, ["食費"], 2026, month=None)
    assert "2026年支出合計: 60,000円" in result
    assert "2026年の支出は**60,000円**でした" in result


# ---------------------------------------------------------------------------
# report_receipt_for_google_chart
# ---------------------------------------------------------------------------


def test_receipt_chart_basic():
    agg = _agg(
        lctg={"収入": 300000},
        mctg={
            "収入": {"ポイント利用": 5000, "キャッシュバック": 3000, "未表示収入": 1000}
        },
        segment={"収入合計": 309000, "支出合計": 0, "収支合計": 309000},
    )
    result = report_receipt_for_google_chart(
        agg, ["ポイント利用", "キャッシュバック"], 2026, 4
    )
    assert "{% googlecharts PieChart 100% %}" in result
    assert "2026年4月収入合計: 309,000円" in result
    assert "'ポイント利用', 5000" in result
    assert "'キャッシュバック', 3000" in result
    assert "'その他', 1000" in result


# ---------------------------------------------------------------------------
# report_blog_balances (統合: 複数 aggregate_balances 呼び出し)
# ---------------------------------------------------------------------------


def test_report_blog_balances_returns_markdown():
    items = list(filter_year_month(_items(), 2026, 4))
    result = report_blog_balances(items, 2026, 4)
    assert "### 実支出内訳（生活費）" in result
    assert "### 実支出内訳（趣味・娯楽）" in result
    assert "### 実支出内訳（特別な支出）" in result
    assert "## 総収支分析" in result
    assert "{% googlecharts PieChart 100% %}" in result


def test_report_blog_balances_with_account_types(tmp_path):
    yaml_path = tmp_path / "account_types.yaml"
    yaml_path.write_text(
        "wallet: []\nprepaid: []\nmall: []\ncreditcard: [カードA]\nbank: [銀行A]\n",
        encoding="utf-8",
    )
    account_types = load_account_types(yaml_path)
    items = list(filter_year_month(_items(), 2026, 4))
    result = report_blog_balances(items, 2026, 4, account_types)
    assert "### 支払方法別の分析" in result
    assert "クレジットカード" in result


# ---------------------------------------------------------------------------
# report_cost_of_living
# ---------------------------------------------------------------------------


def test_report_cost_of_living_returns_table():
    result = report_cost_of_living(_items(), 2026, 4)
    assert "集計期間" in result
    assert "変動費" in result
    assert "固定費" in result
    assert "2026年4月" in result
    assert "2026年累計" in result
