"""seccsv.converter 単体テスト."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from moneyforward.seccsv.cli import main as cli_main
from moneyforward.seccsv.converter import convert, detect_broker

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "seccsv"


def test_detect_broker_known_prefixes():
    assert detect_broker("specificaccountpl_2026.csv") is not None
    assert detect_broker("DetailInquiry_2026.csv") is not None
    assert detect_broker("New_file_2026.csv") is not None
    assert detect_broker("SaveFile_2026.csv") is not None


def test_detect_broker_unknown_returns_none():
    assert detect_broker("random.csv") is None
    assert detect_broker("readme.md") is None


def test_convert_writes_merged_csv(tmp_path: Path):
    # Stage all 4 fixtures into a working dir
    work = tmp_path / "in"
    work.mkdir()
    for f in FIXTURE_DIR.glob("*.csv"):
        shutil.copy(f, work / f.name)

    out = tmp_path / "dividend.csv"
    count = convert(work, out)
    assert count == 5  # 2026/01, 02, 03, 04, 05
    rows = list(csv.reader(out.open(encoding="utf-8", newline="")))
    assert rows[0] == ["集計期間", "配当金・金利収入"]
    body = {r[0]: int(r[1]) for r in rows[1:]}
    assert body["2026/01"] == 12000
    assert body["2026/02"] == 6400 + 2400  # 楽天 + 野村
    assert body["2026/03"] == 3500
    assert body["2026/04"] == 120
    assert body["2026/05"] == 8000


def test_convert_skips_unknown_files(tmp_path: Path):
    work = tmp_path / "in"
    work.mkdir()
    (work / "random.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (work / "DetailInquiry_x.csv").write_text(
        "日付,区分,摘要,銘柄,金額,残高,備考\n2026/06/01,入金,配当金,X,500,500,\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.csv"
    count = convert(work, out)
    assert count == 1


def test_convert_missing_input_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        convert(tmp_path / "missing", tmp_path / "out.csv")


def test_convert_creates_parent_dir(tmp_path: Path):
    work = tmp_path / "in"
    work.mkdir()
    (work / "DetailInquiry_y.csv").write_text(
        "日付,区分,摘要,銘柄,金額,残高,備考\n2026/07/01,入金,配当金,Y,1,1,\n",
        encoding="utf-8",
    )
    out = tmp_path / "deep" / "nested" / "out.csv"
    count = convert(work, out)
    assert count == 1
    assert out.exists()


def test_cli_convert_smoke(tmp_path: Path, capsys: pytest.CaptureFixture):
    work = tmp_path / "in"
    work.mkdir()
    for f in FIXTURE_DIR.glob("*.csv"):
        shutil.copy(f, work / f.name)
    out = tmp_path / "out.csv"
    rc = cli_main(["convert", "--input", str(work), "--output", str(out)])
    assert rc == 0
    assert "wrote" in capsys.readouterr().out
    assert out.exists()
