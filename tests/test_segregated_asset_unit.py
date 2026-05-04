"""segregated_asset モジュール単体テスト."""

from __future__ import annotations

import argparse
import logging
import textwrap
from datetime import date
from pathlib import Path

import pytest

from moneyforward.reports.segregated_asset import (
    apply_adjustments,
    compute_adjustments,
    load_segregated_config,
)

FIXTURE = Path(__file__).parent / "fixtures" / "segregated_asset_sample.yaml"


# ---------------------------------------------------------------------------
# load_segregated_config
# ---------------------------------------------------------------------------


def test_load_returns_segregated_and_debt_lists():
    cfg = load_segregated_config(FIXTURE)
    assert "segregated" in cfg
    assert "debt" in cfg
    assert len(cfg["segregated"]) == 2
    assert len(cfg["debt"]) == 1


def test_load_missing_file_returns_empty():
    cfg = load_segregated_config(Path("/nonexistent/path/does_not_exist.yaml"))
    assert cfg == {"segregated": [], "debt": []}


def test_load_invalid_period_length_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent("""\
        segregated:
          - period: ["2023-01-01"]
            asset_class: "待機資金"
            amount: 100
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="2-element list"):
        load_segregated_config(bad)


def test_load_unlimited_start_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent("""\
        segregated:
          - period: ["unlimited", "2023-12-31"]
            asset_class: "待機資金"
            amount: 100
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unlimited"):
        load_segregated_config(bad)


def test_load_invalid_asset_class_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent("""\
        segregated:
          - period: ["2023-01-01", "unlimited"]
            asset_class: "不明クラス"
            amount: 100
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="asset_class"):
        load_segregated_config(bad)


def test_load_amount_not_int_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent("""\
        segregated:
          - period: ["2023-01-01", "unlimited"]
            asset_class: "待機資金"
            amount: "not_an_int"
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="amount"):
        load_segregated_config(bad)


def test_load_empty_yaml_returns_empty(tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    cfg = load_segregated_config(empty)
    assert cfg == {"segregated": [], "debt": []}


# ---------------------------------------------------------------------------
# compute_adjustments
# ---------------------------------------------------------------------------


def test_compute_unlimited_end_matches_future_date():
    cfg = load_segregated_config(FIXTURE)
    # segregated[0]: ["2023-01-01", "unlimited"], amount=1000000
    adj = compute_adjustments(cfg, date(2099, 12, 31))
    assert adj["segregated"].get("待機資金", 0) == 1000000


def test_compute_before_start_date_excluded():
    cfg = load_segregated_config(FIXTURE)
    # segregated[0] starts 2023-01-01; target before that
    adj = compute_adjustments(cfg, date(2022, 12, 31))
    assert adj["segregated"].get("待機資金", 0) == 0


def test_compute_within_bounded_period():
    cfg = load_segregated_config(FIXTURE)
    # segregated[1]: ["2023-06-01", "2023-12-31"], asset_class=株式（長期）
    adj = compute_adjustments(cfg, date(2023, 9, 15))
    assert adj["segregated"].get("株式（長期）", 0) == 500000


def test_compute_outside_bounded_period():
    cfg = load_segregated_config(FIXTURE)
    # segregated[1]: ["2023-06-01", "2023-12-31"]
    adj = compute_adjustments(cfg, date(2024, 1, 1))
    assert adj["segregated"].get("株式（長期）", 0) == 0


def test_compute_debt_in_range():
    cfg = load_segregated_config(FIXTURE)
    # debt[0]: ["2023-03-01", "2023-03-31"], amount=2000000
    adj = compute_adjustments(cfg, date(2023, 3, 15))
    assert adj["debt"].get("待機資金", 0) == 2000000


def test_compute_debt_out_of_range():
    cfg = load_segregated_config(FIXTURE)
    adj = compute_adjustments(cfg, date(2023, 4, 1))
    assert adj["debt"].get("待機資金", 0) == 0


def test_compute_multiple_entries_same_class_accumulated():
    """同一 asset_class の複数エントリが合算されること."""
    cfg = {
        "segregated": [
            {
                "period": ["2023-01-01", "unlimited"],
                "asset_class": "待機資金",
                "amount": 1000000,
            },
            {
                "period": ["2023-06-01", "unlimited"],
                "asset_class": "待機資金",
                "amount": 500000,
            },
        ],
        "debt": [],
    }
    adj = compute_adjustments(cfg, date(2023, 7, 1))
    assert adj["segregated"]["待機資金"] == 1500000


def test_compute_empty_config_returns_empty_dicts():
    cfg = {"segregated": [], "debt": []}
    adj = compute_adjustments(cfg, date(2024, 1, 1))
    assert adj == {"segregated": {}, "debt": {}}


# ---------------------------------------------------------------------------
# apply_adjustments
# ---------------------------------------------------------------------------


def _base_aggregated() -> dict:
    return {
        "total": 5000000,
        "separate": 0,
        "classes": {
            "生活費": 500000,
            "現金": 500000,
            "待機資金": 2000000,
            "投資信託": 500000,
            "株式（長期）": 1000000,
            "株式（短期）": 0,
            "債券": 500000,
            "FX": 0,
            "先物・オプション": 0,
            "その他の資産": 0,
        },
        "unknown": [],
    }


def test_apply_segregated_adds_to_separate():
    agg = _base_aggregated()
    adj = {"segregated": {"待機資金": 1000000}, "debt": {}}
    result = apply_adjustments(agg, adj)
    assert result["separate"] == 1000000
    # total と classes は変わらない
    assert result["total"] == 5000000
    assert result["classes"]["待機資金"] == 2000000


def test_apply_debt_subtracts_from_total_and_class():
    agg = _base_aggregated()
    adj = {"segregated": {}, "debt": {"待機資金": 2000000}}
    result = apply_adjustments(agg, adj)
    assert result["total"] == 3000000
    assert result["classes"]["待機資金"] == 0


def test_apply_segregated_and_debt_together():
    agg = _base_aggregated()
    adj = {
        "segregated": {"待機資金": 800000},
        "debt": {"待機資金": 1500000},
    }
    result = apply_adjustments(agg, adj)
    assert result["separate"] == 800000
    assert result["total"] == 3500000
    assert result["classes"]["待機資金"] == 500000


def test_apply_does_not_mutate_original():
    agg = _base_aggregated()
    adj = {"segregated": {"待機資金": 100}, "debt": {"待機資金": 200}}
    apply_adjustments(agg, adj)
    assert agg["total"] == 5000000
    assert agg["separate"] == 0
    assert agg["classes"]["待機資金"] == 2000000


def test_apply_no_adjustments_returns_equivalent():
    agg = _base_aggregated()
    result = apply_adjustments(agg, {"segregated": {}, "debt": {}})
    assert result["total"] == agg["total"]
    assert result["separate"] == agg["separate"]
    assert result["classes"] == agg["classes"]


# ---------------------------------------------------------------------------
# CLI smoke: --no-segregated-config で separate=0 のまま
# ---------------------------------------------------------------------------


def test_cli_no_segregated_config_flag(tmp_path):
    """--no-segregated-config 時は分別管理補正なし (separate=0)."""
    from moneyforward.reports.cli import _cmd_asset_allocation

    ns = argparse.Namespace(
        input_dir=tmp_path,
        year=2026,
        month=4,
        day=25,
        no_segregated_config=True,
        segregated_config=FIXTURE,
    )
    # input_dir が空 → items=[] → aggregated["separate"]==0 のまま
    msg = _cmd_asset_allocation(ns)
    assert "分別管理資産=0円" in msg


def test_cli_with_segregated_config_applies_adjustments(tmp_path):
    """設定ファイルあり・対象日に有効エントリが存在する場合、分別管理額が反映される."""
    from moneyforward.reports.cli import _cmd_asset_allocation

    ns = argparse.Namespace(
        input_dir=tmp_path,
        year=2023,
        month=9,
        day=15,
        no_segregated_config=False,
        segregated_config=FIXTURE,
    )
    # FIXTURE segregated[0]=1000000 + segregated[1]=500000 が有効
    msg = _cmd_asset_allocation(ns)
    assert "分別管理資産=1,500,000円" in msg


# ---------------------------------------------------------------------------
# バリデーション追加ケース (Opus レビュー指摘対応)
# ---------------------------------------------------------------------------


def test_load_amount_bool_raises(tmp_path):
    """bool は int のサブクラスだが amount として不可。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent("""\
        segregated:
          - period: ["2023-01-01", "unlimited"]
            asset_class: "待機資金"
            amount: true
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="amount"):
        load_segregated_config(bad)


def test_load_start_after_end_raises(tmp_path):
    """start > end は ValueError。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent("""\
        segregated:
          - period: ["2023-12-31", "2023-01-01"]
            asset_class: "待機資金"
            amount: 100
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="after end"):
        load_segregated_config(bad)


def test_load_unknown_top_level_key_raises(tmp_path):
    """想定外のトップレベルキーは ValueError。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent("""\
        segragated:
          - period: ["2023-01-01", "unlimited"]
            asset_class: "待機資金"
            amount: 100
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown top-level keys"):
        load_segregated_config(bad)


def test_load_top_level_not_dict_raises(tmp_path):
    """YAML ルートが dict でない場合は ValueError。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text("- foo\n- bar\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_segregated_config(bad)


def test_load_note_not_str_raises(tmp_path):
    """note が str 以外の場合は ValueError。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent("""\
        segregated:
          - period: ["2023-01-01", "unlimited"]
            asset_class: "待機資金"
            amount: 100
            note: 12345
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="note"):
        load_segregated_config(bad)


def test_load_yaml_date_type_accepted(tmp_path):
    """PyYAML がクォートなし日付を date 型に変換しても受け付けること。"""
    yaml_file = tmp_path / "dates.yaml"
    yaml_file.write_text(
        textwrap.dedent("""\
        segregated:
          - period: [2023-01-01, unlimited]
            asset_class: "待機資金"
            amount: 500000
        debt: []
        """),
        encoding="utf-8",
    )
    cfg = load_segregated_config(yaml_file)
    assert len(cfg["segregated"]) == 1


def test_compute_negative_amount_accumulated():
    """負値 amount が正しく合算されること (税金仮払い等)。"""
    cfg = {
        "segregated": [
            {
                "period": ["2022-12-22", "unlimited"],
                "asset_class": "待機資金",
                "amount": -300000,
            },
            {
                "period": ["2022-12-23", "unlimited"],
                "asset_class": "待機資金",
                "amount": -750000,
            },
        ],
        "debt": [],
    }
    adj = compute_adjustments(cfg, date(2023, 1, 1))
    assert adj["segregated"]["待機資金"] == -1050000


def test_compute_boundary_start_date_included():
    """start 日ぴったり → 範囲内。"""
    cfg = {
        "segregated": [
            {
                "period": ["2023-06-01", "2023-12-31"],
                "asset_class": "株式（長期）",
                "amount": 500000,
            },
        ],
        "debt": [],
    }
    adj = compute_adjustments(cfg, date(2023, 6, 1))
    assert adj["segregated"].get("株式（長期）", 0) == 500000


def test_compute_boundary_end_date_included():
    """end 日ぴったり → 範囲内。"""
    cfg = {
        "segregated": [
            {
                "period": ["2023-06-01", "2023-12-31"],
                "asset_class": "株式（長期）",
                "amount": 500000,
            },
        ],
        "debt": [],
    }
    adj = compute_adjustments(cfg, date(2023, 12, 31))
    assert adj["segregated"].get("株式（長期）", 0) == 500000


def test_compute_day_after_end_excluded():
    """end + 1 日 → 範囲外。"""
    cfg = {
        "segregated": [
            {
                "period": ["2023-06-01", "2023-12-31"],
                "asset_class": "株式（長期）",
                "amount": 500000,
            },
        ],
        "debt": [],
    }
    adj = compute_adjustments(cfg, date(2024, 1, 1))
    assert adj["segregated"].get("株式（長期）", 0) == 0


def test_apply_debt_unknown_class_raises():
    """aggregated["classes"] に存在しない asset_class で debt 控除すると KeyError。"""
    agg = _base_aggregated()
    adj = {"segregated": {}, "debt": {"先物・オプション_不明": 100000}}
    with pytest.raises(KeyError):
        apply_adjustments(agg, adj)


def test_apply_classes_is_independent_copy():
    """apply_adjustments 後の classes dict が元の classes と独立したオブジェクトであること。"""
    agg = _base_aggregated()
    result = apply_adjustments(agg, {"segregated": {}, "debt": {"待機資金": 1}})
    assert result["classes"] is not agg["classes"]


def test_apply_preserves_unknown_key():
    """apply_adjustments が unknown キーを保持すること。"""
    agg = _base_aggregated()
    agg["unknown"] = [{"asset_type": "weird", "amount_value": 999}]
    result = apply_adjustments(agg, {"segregated": {}, "debt": {}})
    assert result["unknown"] == agg["unknown"]


def test_cli_missing_default_config_does_not_raise(tmp_path, caplog, monkeypatch):
    """デフォルトパスが不在でも例外なし・警告ログが出ること。"""
    import moneyforward.reports.cli as cli_mod
    from moneyforward.reports.cli import _cmd_asset_allocation

    fake_default = tmp_path / "segregated_asset.yaml"  # 存在しないパス
    monkeypatch.setattr(cli_mod, "_DEFAULT_SEGREGATED_CONFIG", fake_default)

    ns = argparse.Namespace(
        input_dir=tmp_path,
        year=2026,
        month=4,
        day=25,
        no_segregated_config=False,
        segregated_config=fake_default,
    )
    with caplog.at_level(logging.WARNING, logger="moneyforward.reports.cli"):
        msg = _cmd_asset_allocation(ns)
    assert "分別管理資産=0円" in msg
    assert any("見つかりません" in r.message for r in caplog.records)


def test_cli_explicit_missing_config_raises(tmp_path):
    """--segregated-config で明示指定したファイルが不在なら FileNotFoundError。"""
    from moneyforward.reports.cli import _cmd_asset_allocation

    ns = argparse.Namespace(
        input_dir=tmp_path,
        year=2026,
        month=4,
        day=25,
        no_segregated_config=False,
        segregated_config=tmp_path / "nonexistent.yaml",
    )
    with pytest.raises(FileNotFoundError):
        _cmd_asset_allocation(ns)
