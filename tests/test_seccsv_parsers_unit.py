"""seccsv._parsers 単体テスト."""

from __future__ import annotations

import csv
from pathlib import Path

from moneyforward.seccsv import _parsers as P

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "seccsv"


def _read(filename: str, encoding: str) -> list[list[str]]:
    with (FIXTURE_DIR / filename).open(encoding=encoding, newline="") as f:
        return list(csv.reader(f))


def test_parse_rakutensec_aggregates_by_month():
    rows = _read("specificaccountpl_anonymized.csv", "cp932")
    monthly = P.parse_rakutensec_profit_and_loss(rows)
    # Jan: (10000+5000) - (2000+1000) = 12000
    assert monthly["2026/01"] == 12000
    # Feb: 8000 - 1600 = 6400 (一般口座は "-" で 0)
    assert monthly["2026/02"] == 6400


def test_parse_sbisec_withdrawal_keeps_dividend_only():
    rows = _read("DetailInquiry_anonymized.csv", "utf-8")
    monthly = P.parse_sbisec_withdrawal_detail(rows)
    # 配当金 + 貸株金利 のみ。出金は除外
    assert monthly["2026/03"] == 3500
    assert monthly["2026/04"] == 120
    # ヘッダ行は処理されない
    assert "日付" not in monthly


def test_parse_nomurasec_picks_dividend_rows():
    rows = _read("New_file_anonymized.csv", "utf-8")
    monthly = P.parse_nomurasec_all_transaction(rows)
    assert monthly == {"2026/02": 2400}


def test_parse_sbisec_transfer_tax_detail_subtracts_tax():
    rows = _read("SaveFile_anonymized.csv", "cp932")
    monthly = P.parse_sbisec_transfer_tax_detail(rows)
    # 配当 +10000、税 +1500 +500 = 2000、差引 8000
    assert monthly["2026/05"] == 8000


def test_safe_int_handles_dash_and_plus():
    assert P._safe_int("-") == 0
    assert P._safe_int("+1,500") == 1500
    assert P._safe_int("") == 0
    assert P._safe_int("3,000") == 3000


def test_merge_monthly_sums_overlapping_keys():
    a = {"2026/01": 100, "2026/02": 200}
    b = {"2026/02": 50, "2026/03": 30}
    merged = P.merge_monthly(a, b)
    assert merged == {"2026/01": 100, "2026/02": 250, "2026/03": 30}
