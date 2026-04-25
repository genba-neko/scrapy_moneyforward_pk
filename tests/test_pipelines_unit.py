"""DynamoDbPipeline: batching + error propagation (no AWS calls)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from scrapy.exceptions import DropItem

from moneyforward_pk.pipelines import DynamoDbPipeline


class _FakeBatchWriter:
    def __init__(self, store: list):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def put_item(self, Item):  # noqa: N803
        self.store.append(Item)


def _make_spider(stats_store):
    spider = MagicMock()
    spider.name = "mf_test"
    spider.logger = MagicMock()
    spider.crawler.stats.inc_value = lambda key, count=1, **_: stats_store.__setitem__(
        key, stats_store.get(key, 0) + count
    )
    return spider


def test_pipeline_flushes_when_batch_full(monkeypatch):
    pipeline = DynamoDbPipeline(table_name="t", batch_n=2, put_delay=0)
    store: list = []
    fake_table = MagicMock()
    fake_table.batch_writer.return_value = _FakeBatchWriter(store)
    pipeline._table = fake_table

    monkeypatch.setattr("time.sleep", lambda *_: None)

    stats: dict[str, int] = {}
    spider = _make_spider(stats)

    pipeline.process_item({"a": 1}, spider)
    assert store == []  # not flushed yet
    pipeline.process_item({"a": 2}, spider)
    assert store == [{"a": 1}, {"a": 2}]
    assert stats["mf_test/dynamodb/put"] == 2


def test_pipeline_flushes_on_close(monkeypatch):
    pipeline = DynamoDbPipeline(table_name="t", batch_n=10, put_delay=0)
    store: list = []
    fake_table = MagicMock()
    fake_table.batch_writer.return_value = _FakeBatchWriter(store)
    pipeline._table = fake_table
    monkeypatch.setattr("time.sleep", lambda *_: None)

    spider = _make_spider({})
    pipeline.process_item({"a": 1}, spider)
    pipeline.close_spider(spider)
    assert store == [{"a": 1}]


def test_pipeline_raises_dropitem_on_failure(monkeypatch):
    pipeline = DynamoDbPipeline(table_name="t", batch_n=1, put_delay=0)
    fake_table = MagicMock()
    fake_table.batch_writer.side_effect = RuntimeError("boom")
    pipeline._table = fake_table
    monkeypatch.setattr("time.sleep", lambda *_: None)

    with pytest.raises(DropItem):
        pipeline.process_item({"a": 1}, _make_spider({}))


def test_from_crawler_requires_table_name():
    crawler = MagicMock()
    crawler.settings.get.return_value = ""
    with pytest.raises(ValueError):
        DynamoDbPipeline.from_crawler(crawler)
