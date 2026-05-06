"""DynamoDB write pipeline for MoneyForward scraper.

Writes items to spider-type-specific DynamoDB tables, maintaining
compatibility with the original scrapy_moneyforward table schema.

Table name is configured per spider_type via environment variables:
  DYNAMODB_TABLE_NAME_TRANSACTION
  DYNAMODB_TABLE_NAME_ASSET_ALLOCATION
  DYNAMODB_TABLE_NAME_ACCOUNT

If all three are unset, the pipeline disables itself via NotConfigured.
If only some are set, spiders whose table name is empty log an info
message and skip DynamoDB writes for that run.
"""

from __future__ import annotations

import logging
import os
from time import sleep
from typing import Any

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem, NotConfigured

from moneyforward.secrets import resolver as _secrets_resolver
from moneyforward.secrets.exceptions import SecretNotFound

logger = logging.getLogger(__name__)

# Per-spider-type primary key definitions (must match the DynamoDB table schema).
# HASH = partition key, RANGE = sort key.
# Used for overwrite_by_pkeys so that batch_writer deduplicates within
# a single AWS batch (up to 25 items); across batches DynamoDB's natural
# PK-based upsert applies.
_PKEYS: dict[str, list[str]] = {
    "transaction": ["year_month", "data_table_sortable_value"],
    "asset_allocation": ["year_month_day", "asset_item_key"],
    "account": ["year_month_day", "account_item_key"],
}


def _get_secret(key: str) -> str | None:
    """Resolve a secret via the project's dual-mode resolver.

    Tries resolver.get() first (env or Bitwarden backend).
    Returns None on SecretNotFound so that boto3's default credential
    chain (~/.aws/config, IAM role, instance profile) can take over.
    """
    try:
        return _secrets_resolver.get(key)
    except SecretNotFound:
        return None


def resolve_dynamodb_resource(dynamodb_resource: Any = None) -> Any:
    """Return a boto3 DynamoDB resource.

    Pass ``dynamodb_resource`` to inject a mock in tests.
    When not provided, resolves credentials via the project's secrets backend
    (env or Bitwarden) and falls back to boto3's default credential chain
    (~/.aws/config, IAM role, instance profile) for any unset key.
    """
    if dynamodb_resource is not None:
        return dynamodb_resource

    import boto3  # type: ignore[import]  # lazy: only when DynamoDB is actually used

    return boto3.resource(
        "dynamodb",
        aws_access_key_id=_get_secret("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=_get_secret("AWS_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("AWS_DEFAULT_REGION") or None,
    )


class DynamoDbPipeline:
    """Batch-write scraped items to DynamoDB.

    Each spider run targets the table configured for its ``spider_type``.
    Items are accumulated in a buffer and flushed when the buffer reaches
    ``DYNAMODB_BATCH_N`` items, or unconditionally on ``close_spider``.

    Compatibility
    -------------
    Table schemas are identical to the original scrapy_moneyforward project:
    - transaction      : HASH=year_month, RANGE=data_table_sortable_value
    - asset_allocation : HASH=year_month_day, RANGE=asset_item_key
    - account          : HASH=year_month_day, RANGE=account_item_key
    """

    def __init__(
        self,
        table_names: dict[str, str],
        put_delay: float,
        batch_n: int,
    ) -> None:
        self.table_names = table_names
        self.put_delay = put_delay
        self.batch_n = batch_n
        self.crawler: Any = None

        self.table: Any = None
        self._spider_type: str = ""
        self._items: list[Any] = []

    @classmethod
    def from_crawler(cls, crawler) -> "DynamoDbPipeline":
        s = crawler.settings
        table_names = {
            "transaction": s.get("DYNAMODB_TABLE_NAME_TRANSACTION", "").strip(),
            "asset_allocation": s.get(
                "DYNAMODB_TABLE_NAME_ASSET_ALLOCATION", ""
            ).strip(),
            "account": s.get("DYNAMODB_TABLE_NAME_ACCOUNT", "").strip(),
        }
        if not any(table_names.values()):
            raise NotConfigured(
                "DynamoDbPipeline disabled: all DYNAMODB_TABLE_NAME_* are unset."
            )
        instance = cls(
            table_names=table_names,
            put_delay=float(s.get("DYNAMODB_PUT_DELAY", 3)),
            batch_n=int(s.get("DYNAMODB_BATCH_N", 10)),
        )
        instance.crawler = crawler
        return instance

    def open_spider(self) -> None:
        spider = self.crawler.spider
        self._spider_type = getattr(spider, "spider_type", spider.name)
        self._items = []  # reset buffer on each spider open
        table_name = self.table_names.get(self._spider_type, "")
        if not table_name:
            logger.info(
                "DynamoDbPipeline: no table configured for spider_type=%r; "
                "DynamoDB writes will be skipped for this run.",
                self._spider_type,
            )
            self.table = None
            return
        db = resolve_dynamodb_resource()
        self.table = db.Table(table_name)
        logger.info(
            "DynamoDbPipeline open: spider_type=%r table=%r",
            self._spider_type,
            table_name,
        )

    def _batch_flush(self, is_force: bool = False) -> None:
        if self.table is None:
            return
        if not (is_force or len(self._items) >= self.batch_n):
            return
        if not self._items:
            return

        # Snapshot the buffer before the AWS call so that on failure the buffer
        # is already empty and subsequent items start a fresh batch.
        items, self._items = self._items, []

        pkeys = _PKEYS.get(self._spider_type, [])
        kwargs: dict[str, Any] = {}
        if pkeys:
            kwargs["overwrite_by_pkeys"] = pkeys

        try:
            with self.table.batch_writer(**kwargs) as batch:
                for item in items:
                    record = ItemAdapter(item).asdict()
                    batch.put_item(record)
                    if self.crawler is not None:
                        self.crawler.stats.inc_value("moneyforward/dynamodb/items")
        except Exception as err:
            logger.error("DynamoDB write error: %s", err)
            if self.crawler is not None:
                self.crawler.stats.inc_value("moneyforward/dynamodb/errors")
            raise DropItem(f"DynamoDB write error: {err}") from err
        finally:
            sleep(self.put_delay)

    def close_spider(self) -> None:
        self._batch_flush(is_force=True)
        self.table = None

    def process_item(self, item: Any) -> Any:
        if self.table is None:
            return item
        self._items.append(item)
        self._batch_flush()
        return item
