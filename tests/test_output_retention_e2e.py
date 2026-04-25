"""End-to-end retention test for ``JsonOutputPipeline``.

The unit test in ``test_pipelines_unit.py`` covers retention with a
single fixture file. This module simulates the full lifecycle: a
spider opens against a directory containing 30 days of historical
JSONL outputs and we assert that exactly the files older than
``retention_days`` are unlinked, fresh files survive, and unrelated
files belonging to other spiders are not touched. Designed to mirror
real CI behaviour where ``runtime/output/`` accumulates over weeks.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from moneyforward_pk.pipelines import JsonOutputPipeline


def _make_spider(name: str = "mf_test") -> MagicMock:
    spider = MagicMock()
    spider.name = name
    spider.logger = MagicMock()
    spider.crawler.stats.set_value = MagicMock()
    return spider


def _write_jsonl(path: Path, age_days: float, payload: dict | None = None) -> Path:
    """Write a single-line JSONL fixture and back-date its mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload or {"k": "v"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    epoch = time.time() - age_days * 86400
    os.utime(path, (epoch, epoch))
    return path


def test_e2e_retention_prunes_old_keeps_recent(tmp_path: Path):
    spider_name = "mf_transaction"
    out_dir = tmp_path / "output"
    out_dir.mkdir()

    # 30 days of fixtures: ages 0..29, one per day.
    fixtures = []
    for age in range(30):
        p = _write_jsonl(
            out_dir / f"{spider_name}_2025{age:02d}_age{age:02d}.jsonl", age_days=age
        )
        fixtures.append((p, age))

    # Unrelated spider fixture must survive even though it is ancient.
    other = _write_jsonl(out_dir / "mf_account_old.jsonl", age_days=999)
    # Also a non-jsonl junk file unrelated to spider name; must survive.
    junk = out_dir / "README.txt"
    junk.write_text("keep me", encoding="utf-8")
    os.utime(junk, (time.time() - 365 * 86400, time.time() - 365 * 86400))

    pipeline = JsonOutputPipeline(
        output_dir=out_dir,
        template="{spider}_today.jsonl",
        retention_days=14,
    )
    pipeline.open_spider(_make_spider(spider_name))
    pipeline.close_spider(_make_spider(spider_name))

    surviving_targets = {p for p, age in fixtures if age < 14}
    deleted_targets = {p for p, age in fixtures if age >= 14}

    for path in surviving_targets:
        assert path.exists(), f"recent fixture must survive: {path.name}"
    for path in deleted_targets:
        assert not path.exists(), f"old fixture must be pruned: {path.name}"

    # Cross-spider isolation: other spider's file untouched.
    assert other.exists()
    # Non-prefix-matching junk untouched.
    assert junk.exists()


def test_e2e_retention_zero_disables_pruning(tmp_path: Path):
    spider_name = "mf_account"
    out_dir = tmp_path / "output"
    old = _write_jsonl(out_dir / f"{spider_name}_ancient.jsonl", age_days=400)

    pipeline = JsonOutputPipeline(
        output_dir=out_dir,
        template="{spider}_today.jsonl",
        retention_days=0,
    )
    pipeline.open_spider(_make_spider(spider_name))
    pipeline.close_spider(_make_spider(spider_name))

    # retention_days <= 0 must short-circuit; the ancient file survives.
    assert old.exists()


def test_e2e_retention_survives_locked_file(tmp_path: Path, monkeypatch):
    """If unlink raises OSError, retention logs and continues, never aborts."""
    spider_name = "mf_asset_allocation"
    out_dir = tmp_path / "output"
    locked = _write_jsonl(out_dir / f"{spider_name}_locked.jsonl", age_days=90)
    survivor_old = _write_jsonl(out_dir / f"{spider_name}_old.jsonl", age_days=90)

    real_unlink = Path.unlink

    def flaky_unlink(self, *args, **kwargs):
        if self.name.endswith("_locked.jsonl"):
            raise PermissionError("file in use")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    pipeline = JsonOutputPipeline(
        output_dir=out_dir,
        template="{spider}_today.jsonl",
        retention_days=14,
    )
    # open_spider must NOT raise even though one file fails to unlink.
    pipeline.open_spider(_make_spider(spider_name))
    pipeline.close_spider(_make_spider(spider_name))

    assert locked.exists()  # could not be deleted, but pipeline survived
    assert not survivor_old.exists()  # the deletable old file was pruned


def test_e2e_retention_handles_empty_output_dir(tmp_path: Path):
    """First run on a fresh checkout: output dir doesn't exist yet."""
    spider_name = "mf_transaction"
    out_dir = tmp_path / "output_does_not_exist_yet"

    pipeline = JsonOutputPipeline(
        output_dir=out_dir,
        template="{spider}_today.jsonl",
        retention_days=14,
    )
    pipeline.open_spider(_make_spider(spider_name))
    pipeline.close_spider(_make_spider(spider_name))

    # Pipeline created the directory and a fresh output file.
    assert out_dir.exists()
    assert any(out_dir.glob("*.jsonl"))


@pytest.mark.parametrize("retention_days", [1, 7, 30])
def test_e2e_retention_threshold_boundary(tmp_path: Path, retention_days):
    """File on retention boundary minus 1 hour survives; plus 1 hour does not."""
    spider_name = "mf_transaction"
    out_dir = tmp_path / "output"
    just_inside = _write_jsonl(
        out_dir / f"{spider_name}_inside.jsonl",
        age_days=retention_days - (1 / 24),
    )
    just_outside = _write_jsonl(
        out_dir / f"{spider_name}_outside.jsonl",
        age_days=retention_days + (1 / 24),
    )

    pipeline = JsonOutputPipeline(
        output_dir=out_dir,
        template="{spider}_today.jsonl",
        retention_days=retention_days,
    )
    pipeline.open_spider(_make_spider(spider_name))
    pipeline.close_spider(_make_spider(spider_name))

    assert just_inside.exists()
    assert not just_outside.exists()
