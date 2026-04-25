"""reports.cli 単体テスト。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from moneyforward_pk.reports.cli import main

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "reports"


@pytest.fixture
def transaction_dir(tmp_path: Path) -> Path:
    """JSONL fixture を spider 名 prefix にリネームした作業ディレクトリ。"""
    src = FIXTURE_DIR / "sample_transactions.jsonl"
    dst = tmp_path / "mf_transaction_20260425.jsonl"
    shutil.copyfile(src, dst)
    return tmp_path


@pytest.fixture
def asset_allocation_dir(tmp_path: Path) -> Path:
    src = FIXTURE_DIR / "sample_asset_allocation.jsonl"
    dst = tmp_path / "mf_asset_allocation_20260425.jsonl"
    shutil.copyfile(src, dst)
    return tmp_path


def test_cli_balances_renders_summary(
    transaction_dir: Path, capsys: pytest.CaptureFixture
):
    rc = main(
        [
            "--input-dir",
            str(transaction_dir),
            "balances",
            "--year",
            "2026",
            "--month",
            "4",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "総計" in out
    assert "(2026/4)" in out
    assert "収入合計: 300,000円" in out


def test_cli_asset_allocation_renders(
    asset_allocation_dir: Path, capsys: pytest.CaptureFixture
):
    rc = main(
        [
            "--input-dir",
            str(asset_allocation_dir),
            "asset_allocation",
            "--year",
            "2026",
            "--month",
            "4",
            "--day",
            "25",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "アセットアロケーション" in out
    assert "総資産額=1,500,000円" in out


def test_cli_balances_csv_writes_file(transaction_dir: Path, tmp_path: Path):
    out_file = tmp_path / "out" / "report_2026.csv"
    rc = main(
        [
            "--input-dir",
            str(transaction_dir),
            "balances_csv",
            "--year",
            "2026",
            "--output",
            str(out_file),
        ]
    )
    assert rc == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8-sig")
    assert "分類,期間合計" in content
    assert "2026年4月" in content


def test_cli_balances_slack_flag_does_not_raise(transaction_dir: Path, monkeypatch):
    """--slack 指定時、webhook 未設定なら no-op (例外を投げない)。"""
    monkeypatch.delenv("SLACK_INCOMING_WEBHOOK_URL", raising=False)
    rc = main(
        [
            "--input-dir",
            str(transaction_dir),
            "--slack",
            "balances",
            "--year",
            "2026",
            "--month",
            "4",
        ]
    )
    assert rc == 0
