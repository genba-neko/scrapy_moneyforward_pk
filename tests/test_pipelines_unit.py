"""JsonArrayOutputPipeline + path-resolution helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from moneyforward.pipelines import JsonArrayOutputPipeline
from moneyforward.utils.paths import (
    PROJECT_ROOT,
    resolve_output_dir,
    sanitize_spider_name,
)


def _make_spider(
    name: str = "transaction", spider_type: str = "transaction"
) -> MagicMock:
    spider = MagicMock()
    spider.name = name
    spider.spider_type = spider_type
    spider.logger = MagicMock()
    spider.crawler.stats.set_value = MagicMock()
    return spider


# ----------------------------------------------------------- pipeline behavior


def test_pipeline_appends_items_to_pre_initialized_file(tmp_path: Path) -> None:
    """Orchestrator init writes ``[``; pipeline appends items separated by ``,``."""
    pre = tmp_path / "moneyforward_transaction.json"
    pre.write_text("[", encoding="utf-8")

    pipeline = JsonArrayOutputPipeline(
        output_dir=tmp_path,
        template="moneyforward_{spider_type}.json",
    )
    spider = _make_spider()
    pipeline.open_spider(spider)
    pipeline.process_item({"a": 1, "b": "あ"}, spider)
    pipeline.process_item({"a": 2}, spider)
    pipeline.close_spider(spider)

    text = pre.read_text(encoding="utf-8")
    # Without the closing ``]`` the file is not yet valid JSON; closing is the
    # orchestrator's responsibility. We test the array body here.
    assert text == '[\n  {\n    "a": 1,\n    "b": "あ"\n  },\n  {\n    "a": 2\n  }'


def test_pipeline_continues_appending_across_invocations(tmp_path: Path) -> None:
    """Second pipeline invocation must prepend ``,`` before its first item."""
    pre = tmp_path / "moneyforward_transaction.json"
    pre.write_text("[", encoding="utf-8")

    pipeline_a = JsonArrayOutputPipeline(
        output_dir=tmp_path,
        template="moneyforward_{spider_type}.json",
    )
    spider = _make_spider()
    pipeline_a.open_spider(spider)
    pipeline_a.process_item({"a": 1}, spider)
    pipeline_a.close_spider(spider)

    pipeline_b = JsonArrayOutputPipeline(
        output_dir=tmp_path,
        template="moneyforward_{spider_type}.json",
    )
    pipeline_b.open_spider(spider)
    pipeline_b.process_item({"b": 2}, spider)
    pipeline_b.close_spider(spider)

    # Append the closing bracket the way the orchestrator would.
    pre.write_text(pre.read_text(encoding="utf-8") + "]", encoding="utf-8")
    assert json.loads(pre.read_text(encoding="utf-8")) == [{"a": 1}, {"b": 2}]


def test_pipeline_self_initializes_when_file_missing(tmp_path: Path) -> None:
    """Standalone ``scrapy crawl <name>`` (no orchestrator init) still works."""
    pipeline = JsonArrayOutputPipeline(
        output_dir=tmp_path,
        template="moneyforward_{spider_type}.json",
    )
    spider = _make_spider()
    pipeline.open_spider(spider)
    pipeline.process_item({"x": 1}, spider)
    pipeline.close_spider(spider)

    out = tmp_path / "moneyforward_transaction.json"
    assert out.read_text(encoding="utf-8") == '[\n  {\n    "x": 1\n  }'


def test_pipeline_records_path_in_stats(tmp_path: Path) -> None:
    pipeline = JsonArrayOutputPipeline(
        output_dir=tmp_path,
        template="moneyforward_{spider_type}.json",
    )
    spider = _make_spider()
    pipeline.open_spider(spider)
    pipeline.close_spider(spider)
    spider.crawler.stats.set_value.assert_any_call(
        "transaction/output/path",
        str(tmp_path / "moneyforward_transaction.json"),
    )


def test_pipeline_process_item_before_open_raises() -> None:
    pipeline = JsonArrayOutputPipeline(
        output_dir=Path("."),
        template="moneyforward_{spider_type}.json",
    )
    with pytest.raises(RuntimeError):
        pipeline.process_item({"a": 1}, _make_spider())


def test_from_crawler_uses_settings() -> None:
    crawler = MagicMock()
    test_dir = PROJECT_ROOT / "runtime" / "output_test"
    crawler.settings.get.side_effect = lambda key, default=None: {
        "OUTPUT_DIR": str(test_dir),
        "OUTPUT_DIR_DEFAULT": "runtime/output",
        "OUTPUT_FILENAME_TEMPLATE": "moneyforward_{spider_type}.json",
    }.get(key, default)
    pipeline = JsonArrayOutputPipeline.from_crawler(crawler)
    assert pipeline.output_dir == test_dir.resolve()
    assert pipeline.template == "moneyforward_{spider_type}.json"


# ----------------------------------------------------------- path utilities


def test_resolve_output_dir_rejects_path_outside_project(tmp_path: Path) -> None:
    outside = tmp_path / "leak"
    with pytest.raises(ValueError):
        resolve_output_dir(str(outside), default=PROJECT_ROOT / "runtime" / "output")


def test_resolve_output_dir_uses_default_when_blank() -> None:
    default = PROJECT_ROOT / "runtime" / "output"
    resolved = resolve_output_dir("", default=default)
    assert resolved == default.resolve()


def test_resolve_output_dir_accepts_relative_under_project(tmp_path: Path) -> None:
    relative = "runtime/output/sub"
    resolved = resolve_output_dir(relative, default=PROJECT_ROOT / "runtime" / "output")
    assert resolved.is_relative_to(PROJECT_ROOT.resolve())


def test_sanitize_spider_name_replaces_unsafe_chars() -> None:
    assert sanitize_spider_name("../../etc/passwd") == "______etc_passwd"
    assert sanitize_spider_name("good_name-1") == "good_name-1"
    assert sanitize_spider_name("") == "spider"
    assert "/" not in sanitize_spider_name("///")
    assert ".." not in sanitize_spider_name("../foo")
