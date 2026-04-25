"""JsonOutputPipeline: per-spider JSON Lines writer + path safety."""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from moneyforward_pk.pipelines import JsonOutputPipeline
from moneyforward_pk.utils.paths import (
    PROJECT_ROOT,
    ensure_unique_path,
    resolve_output_dir,
    resolve_output_path,
    sanitize_spider_name,
)


def _make_spider(name: str = "mf_test") -> MagicMock:
    spider = MagicMock()
    spider.name = name
    spider.logger = MagicMock()
    spider.crawler.stats.set_value = MagicMock()
    return spider


def test_pipeline_writes_jsonl(tmp_path: Path):
    pipeline = JsonOutputPipeline(output_dir=tmp_path, template="{spider}.jsonl")
    spider = _make_spider("mf_test")

    pipeline.open_spider(spider)
    pipeline.process_item({"a": 1, "b": "あ"}, spider)
    pipeline.process_item({"a": 2}, spider)
    pipeline.close_spider(spider)

    out = tmp_path / "mf_test.jsonl"
    assert out.exists()
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1, "b": "あ"}
    assert json.loads(lines[1]) == {"a": 2}


def test_pipeline_records_path_in_stats(tmp_path: Path):
    pipeline = JsonOutputPipeline(output_dir=tmp_path, template="{spider}.jsonl")
    spider = _make_spider("mf_test")
    pipeline.open_spider(spider)
    pipeline.close_spider(spider)
    spider.crawler.stats.set_value.assert_any_call(
        "mf_test/output/path", str(tmp_path / "mf_test.jsonl")
    )
    spider.crawler.stats.set_value.assert_any_call("mf_test/output/items", 0)


def test_pipeline_avoids_overwriting_existing_file(tmp_path: Path):
    (tmp_path / "mf_test.jsonl").write_text("preexisting", encoding="utf-8")
    pipeline = JsonOutputPipeline(output_dir=tmp_path, template="{spider}.jsonl")
    spider = _make_spider("mf_test")

    pipeline.open_spider(spider)
    pipeline.process_item({"x": 1}, spider)
    pipeline.close_spider(spider)

    assert (tmp_path / "mf_test.jsonl").read_text(encoding="utf-8") == "preexisting"
    rotated = tmp_path / "mf_test-1.jsonl"
    assert rotated.exists()
    assert json.loads(rotated.read_text(encoding="utf-8").strip()) == {"x": 1}


def test_pipeline_process_item_before_open_raises():
    pipeline = JsonOutputPipeline(output_dir=Path("."), template="{spider}.jsonl")
    with pytest.raises(RuntimeError):
        pipeline.process_item({"a": 1}, _make_spider())


def test_resolve_output_dir_rejects_path_outside_project(tmp_path: Path):
    outside = tmp_path / "leak"
    with pytest.raises(ValueError):
        resolve_output_dir(str(outside), default=PROJECT_ROOT / "runtime" / "output")


def test_resolve_output_dir_uses_default_when_blank():
    default = PROJECT_ROOT / "runtime" / "output"
    resolved = resolve_output_dir("", default=default)
    assert resolved == default.resolve()


def test_resolve_output_dir_accepts_relative_under_project(tmp_path: Path, monkeypatch):
    relative = "runtime/output/sub"
    resolved = resolve_output_dir(relative, default=PROJECT_ROOT / "runtime" / "output")
    assert resolved.is_relative_to(PROJECT_ROOT.resolve())


def test_resolve_output_path_renders_template():
    out = resolve_output_path(
        "mf_transaction",
        Path("/tmp/out"),
        "{spider}_{date:%Y%m%d}.jsonl",
        today=date(2025, 1, 15),
    )
    assert out.name == "mf_transaction_20250115.jsonl"


def test_ensure_unique_path_rotates(tmp_path: Path):
    base = tmp_path / "x.jsonl"
    base.write_text("a", encoding="utf-8")
    rotated = ensure_unique_path(base)
    assert rotated.name == "x-1.jsonl"
    rotated.write_text("b", encoding="utf-8")
    rotated2 = ensure_unique_path(base)
    assert rotated2.name == "x-2.jsonl"


def test_from_crawler_uses_settings(tmp_path: Path, monkeypatch):
    crawler = MagicMock()
    # Force the resolved path under PROJECT_ROOT by using a path inside it.
    test_dir = PROJECT_ROOT / "runtime" / "output_test"
    crawler.settings.get.side_effect = lambda key, default=None: {
        "OUTPUT_DIR": str(test_dir),
        "OUTPUT_DIR_DEFAULT": "runtime/output",
        "OUTPUT_FILENAME_TEMPLATE": "{spider}.jsonl",
    }.get(key, default)
    crawler.settings.getint.side_effect = lambda key, default=None: {
        "OUTPUT_RETENTION_DAYS": 7,
    }.get(key, default)
    pipeline = JsonOutputPipeline.from_crawler(crawler)
    assert pipeline.output_dir == test_dir.resolve()
    assert pipeline.template == "{spider}.jsonl"
    assert pipeline.retention_days == 7


def test_pipeline_prunes_files_older_than_retention(tmp_path: Path):
    """open_spider must unlink stale files but keep recent ones."""
    pipeline = JsonOutputPipeline(
        output_dir=tmp_path,
        template="{spider}_{date:%Y%m%d}.jsonl",
        retention_days=7,
    )
    spider = _make_spider("mf_test")

    stale = tmp_path / "mf_test_20200101.jsonl"
    fresh = tmp_path / "mf_test_20991231.jsonl"
    other = tmp_path / "mf_other_20200101.jsonl"
    for path in (stale, fresh, other):
        path.write_text("x", encoding="utf-8")

    old_mtime = time.time() - 30 * 86400
    fresh_mtime = time.time() - 1 * 86400
    os.utime(stale, (old_mtime, old_mtime))
    os.utime(fresh, (fresh_mtime, fresh_mtime))
    os.utime(other, (old_mtime, old_mtime))

    pipeline.open_spider(spider)
    pipeline.close_spider(spider)

    assert not stale.exists(), "stale mf_test file should be removed"
    assert fresh.exists(), "recent mf_test file must be retained"
    # Other-spider file must not be touched even when older than retention.
    assert other.exists(), "other-spider files must not be pruned"


def test_pipeline_retention_zero_disables_pruning(tmp_path: Path):
    pipeline = JsonOutputPipeline(
        output_dir=tmp_path,
        template="{spider}.jsonl",
        retention_days=0,
    )
    spider = _make_spider("mf_test")
    stale = tmp_path / "mf_test_old.jsonl"
    stale.write_text("x", encoding="utf-8")
    os.utime(stale, (0, 0))

    pipeline.open_spider(spider)
    pipeline.close_spider(spider)
    # Retention disabled: no unlink even though the file is decades old.
    assert stale.exists()


def test_sanitize_spider_name_replaces_unsafe_chars():
    # ".." (2) + "/" (1) + ".." (2) + "/" (1) + "etc/passwd" -> 6 underscores.
    assert sanitize_spider_name("../../etc/passwd") == "______etc_passwd"
    assert sanitize_spider_name("good_name-1") == "good_name-1"
    assert sanitize_spider_name("") == "spider"
    assert "/" not in sanitize_spider_name("///")
    assert ".." not in sanitize_spider_name("../foo")


def test_resolve_output_path_uses_sanitized_spider_name(tmp_path: Path):
    """Path traversal attempts collapse to safe characters before joining."""
    out = resolve_output_path(
        "../escape",
        tmp_path,
        "{spider}.jsonl",
        today=date(2025, 1, 15),
    )
    # Result must remain inside tmp_path; sanitize replaces ../ with safe chars.
    assert out.parent == tmp_path
    assert ".." not in out.name
