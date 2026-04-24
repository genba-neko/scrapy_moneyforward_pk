"""Scrapy pipelines for MoneyForward scraper."""

from __future__ import annotations

import logging
import time
from typing import Any

from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)


class DynamoDbPipeline:
    """Batches items and writes to DynamoDB.

    Table name resolved from ``DYNAMODB_TABLE_NAME`` (setting or env).
    Items batched to ``DYNAMODB_BATCH_N`` and flushed with ``batch_writer``.
    Sleeps ``DYNAMODB_PUT_DELAY`` seconds between batches to throttle writes.
    """

    def __init__(self, table_name: str, batch_n: int, put_delay: float) -> None:
        self.table_name = table_name
        self.batch_n = batch_n
        self.put_delay = put_delay
        self._buffer: list[dict[str, Any]] = []
        self._table = None

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        table_name = settings.get("DYNAMODB_TABLE_NAME")
        if not table_name:
            raise ValueError("DYNAMODB_TABLE_NAME setting is required")
        return cls(
            table_name=table_name,
            batch_n=int(settings.getint("DYNAMODB_BATCH_N", 10)),
            put_delay=float(settings.getfloat("DYNAMODB_PUT_DELAY", 3.0)),
        )

    def open_spider(self, spider) -> None:
        import boto3  # lazy import; tests may not have boto3 creds

        self._table = boto3.resource("dynamodb").Table(self.table_name)  # type: ignore[attr-defined]
        spider.logger.info(
            "DynamoDbPipeline open: table=%s batch=%d delay=%.1fs",
            self.table_name,
            self.batch_n,
            self.put_delay,
        )

    def close_spider(self, spider) -> None:
        if self._buffer:
            self._flush(spider)

    def process_item(self, item, spider):
        self._buffer.append(dict(item))
        if len(self._buffer) >= self.batch_n:
            self._flush(spider)
        return item

    def _flush(self, spider) -> None:
        if not self._buffer or self._table is None:
            self._buffer.clear()
            return
        batch = self._buffer
        self._buffer = []
        try:
            with self._table.batch_writer() as writer:
                for record in batch:
                    writer.put_item(Item=record)
            stats = getattr(spider.crawler, "stats", None) if spider.crawler else None
            if stats is not None:
                stats.inc_value(f"{spider.name}/dynamodb/put", count=len(batch))
            time.sleep(self.put_delay)
        except Exception as exc:  # noqa: BLE001
            logger.exception("DynamoDB batch write failed: %s", exc)
            raise DropItem(f"DynamoDB write failed: {exc}") from exc
