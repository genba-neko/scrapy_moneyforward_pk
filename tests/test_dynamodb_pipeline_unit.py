"""Unit tests for DynamoDbPipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from scrapy.exceptions import DropItem, NotConfigured

from moneyforward.pipelines.dynamodb import _PKEYS, DynamoDbPipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeStats:
    def __init__(self):
        self._values: dict[str, int] = {}

    def inc_value(self, key, count=1, start=0):
        self._values[key] = self._values.get(key, start) + count

    def get_value(self, key, default=0):
        return self._values.get(key, default)


def _make_pipeline(
    spider_type: str = "transaction",
    batch_n: int = 2,
    put_delay: float = 0,
    table_names: dict[str, str] | None = None,
) -> tuple[DynamoDbPipeline, MagicMock]:
    """Return (pipeline, fake_batch) with a pre-wired mock table."""
    if table_names is None:
        table_names = {
            "transaction": "mf_transaction",
            "asset_allocation": "mf_asset_allocation",
            "account": "mf_account",
        }
    pipeline = DynamoDbPipeline(
        table_names=table_names,
        put_delay=put_delay,
        batch_n=batch_n,
    )
    pipeline.crawler = MagicMock()
    pipeline.crawler.stats = FakeStats()
    pipeline._spider_type = spider_type

    fake_batch = MagicMock()
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_batch
    fake_ctx.__exit__.return_value = False

    fake_table = MagicMock()
    fake_table.batch_writer.return_value = fake_ctx
    pipeline.table = fake_table

    return pipeline, fake_batch


def _make_transaction_item(sort_val: str = "20260401_001") -> dict:
    return {
        "year_month": "202604",
        "data_table_sortable_value": sort_val,
        "is_active": True,
        "year": 2026,
        "month": 4,
        "day": 1,
        "date": "2026-04-01",
        "content": "テスト",
        "amount_number": -1000,
        "amount_view": "-1,000",
        "transaction_account": "銀行",
        "transaction_transfer": "",
        "transaction_detail": "",
        "lctg": "食費",
        "mctg": "食料品",
        "memo": "",
    }


def _make_crawler(
    transaction: str = "mf_transaction",
    asset_allocation: str = "",
    account: str = "",
) -> MagicMock:
    crawler = MagicMock()
    crawler.settings.get.side_effect = lambda key, default=None: {
        "DYNAMODB_TABLE_NAME_TRANSACTION": transaction,
        "DYNAMODB_TABLE_NAME_ASSET_ALLOCATION": asset_allocation,
        "DYNAMODB_TABLE_NAME_ACCOUNT": account,
        "DYNAMODB_PUT_DELAY": 0,
        "DYNAMODB_BATCH_N": 10,
    }.get(key, default)
    return crawler


# ---------------------------------------------------------------------------
# from_crawler
# ---------------------------------------------------------------------------


def test_from_crawler_raises_not_configured_when_all_table_names_empty():
    crawler = _make_crawler(transaction="", asset_allocation="", account="")
    with pytest.raises(NotConfigured):
        DynamoDbPipeline.from_crawler(crawler)


def test_from_crawler_raises_not_configured_for_whitespace_only_names():
    """Whitespace-only names should be treated as unset (M2 fix)."""
    crawler = _make_crawler(transaction="  ", asset_allocation="", account="")
    with pytest.raises(NotConfigured):
        DynamoDbPipeline.from_crawler(crawler)


def test_from_crawler_succeeds_when_any_table_name_set():
    crawler = _make_crawler(transaction="mf_transaction")
    pipeline = DynamoDbPipeline.from_crawler(crawler)
    assert pipeline.table_names["transaction"] == "mf_transaction"
    assert pipeline.table_names["asset_allocation"] == ""
    assert pipeline.crawler is crawler


def test_from_crawler_strips_table_names():
    crawler = _make_crawler(transaction="  mf_transaction  ")
    pipeline = DynamoDbPipeline.from_crawler(crawler)
    assert pipeline.table_names["transaction"] == "mf_transaction"


# ---------------------------------------------------------------------------
# open_spider
# ---------------------------------------------------------------------------


def test_open_spider_sets_table_when_table_name_configured():
    pipeline = DynamoDbPipeline(
        table_names={
            "transaction": "mf_transaction",
            "asset_allocation": "",
            "account": "",
        },
        put_delay=0,
        batch_n=10,
    )
    spider = MagicMock()
    spider.spider_type = "transaction"
    pipeline.crawler = MagicMock()
    pipeline.crawler.spider = spider

    mock_table = MagicMock()
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    with patch(
        "moneyforward.pipelines.dynamodb.resolve_dynamodb_resource",
        return_value=mock_resource,
    ):
        pipeline.open_spider()

    assert pipeline.table is mock_table
    mock_resource.Table.assert_called_once_with("mf_transaction")


def test_open_spider_leaves_table_none_when_table_name_empty():
    pipeline = DynamoDbPipeline(
        table_names={"transaction": "", "asset_allocation": "", "account": ""},
        put_delay=0,
        batch_n=10,
    )
    spider = MagicMock()
    spider.spider_type = "transaction"
    pipeline.crawler = MagicMock()
    pipeline.crawler.spider = spider

    with patch("moneyforward.pipelines.dynamodb.resolve_dynamodb_resource") as mock_res:
        pipeline.open_spider()

    mock_res.assert_not_called()
    assert pipeline.table is None


def test_open_spider_resets_buffer():
    """T4: open_spider clears stale items from a previous spider run."""
    pipeline, _ = _make_pipeline(batch_n=100)
    pipeline._items = [_make_transaction_item()]  # simulate stale state

    spider = MagicMock()
    spider.spider_type = "transaction"
    pipeline.crawler = MagicMock()
    pipeline.crawler.spider = spider
    mock_resource = MagicMock()
    mock_resource.Table.return_value = MagicMock()

    with patch(
        "moneyforward.pipelines.dynamodb.resolve_dynamodb_resource",
        return_value=mock_resource,
    ):
        pipeline.open_spider()

    assert pipeline._items == []


# ---------------------------------------------------------------------------
# process_item + _batch_flush
# ---------------------------------------------------------------------------


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_process_item_flushes_when_batch_size_reached(mock_sleep):
    pipeline, fake_batch = _make_pipeline(batch_n=2)
    item1 = _make_transaction_item("20260401_001")
    item2 = _make_transaction_item("20260401_002")

    pipeline.process_item(item1)
    assert fake_batch.put_item.call_count == 0

    pipeline.process_item(item2)
    assert fake_batch.put_item.call_count == 2
    assert pipeline.crawler.stats.get_value("moneyforward/dynamodb/items") == 2
    assert pipeline._items == []
    mock_sleep.assert_called_once_with(0)


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_process_item_no_flush_before_batch_size(mock_sleep):
    pipeline, fake_batch = _make_pipeline(batch_n=5)
    pipeline.process_item(_make_transaction_item())
    assert fake_batch.put_item.call_count == 0
    mock_sleep.assert_not_called()


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_process_item_multiple_flushes_across_batches(mock_sleep):
    """T1: 5 items with batch_n=2 → 2 flushes + 1 remaining on close_spider."""
    pipeline, fake_batch = _make_pipeline(batch_n=2)
    for i in range(5):
        pipeline.process_item(_make_transaction_item(f"20260401_{i:03}"))

    # After 5 items: 2 flushes of 2 items each = 4 PUT calls, 1 item buffered
    assert fake_batch.put_item.call_count == 4
    assert len(pipeline._items) == 1
    assert mock_sleep.call_count == 2

    pipeline.close_spider()
    assert fake_batch.put_item.call_count == 5
    assert pipeline._items == []


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_close_spider_flushes_remaining_items(mock_sleep):
    pipeline, fake_batch = _make_pipeline(batch_n=10)
    pipeline.process_item(_make_transaction_item())

    pipeline.close_spider()

    assert fake_batch.put_item.call_count == 1
    assert pipeline.crawler.stats.get_value("moneyforward/dynamodb/items") == 1
    assert pipeline.table is None


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_close_spider_noop_when_buffer_empty(mock_sleep):
    pipeline, fake_batch = _make_pipeline(batch_n=10)
    pipeline.close_spider()
    fake_batch.put_item.assert_not_called()


# ---------------------------------------------------------------------------
# table=None (no-op) path
# ---------------------------------------------------------------------------


def test_process_item_passthrough_when_table_none():
    pipeline, _ = _make_pipeline()
    pipeline.table = None
    item = _make_transaction_item()
    result = pipeline.process_item(item)
    assert result is item
    assert pipeline._items == []


def test_close_spider_noop_when_table_none():
    pipeline, fake_batch = _make_pipeline()
    pipeline.table = None
    pipeline.close_spider()
    fake_batch.put_item.assert_not_called()


# ---------------------------------------------------------------------------
# overwrite_by_pkeys
# ---------------------------------------------------------------------------


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_batch_writer_called_with_overwrite_pkeys_for_transaction(_sleep):
    pipeline, _ = _make_pipeline(spider_type="transaction", batch_n=1)
    pipeline.process_item(_make_transaction_item())
    pipeline.table.batch_writer.assert_called_once_with(
        overwrite_by_pkeys=["year_month", "data_table_sortable_value"]
    )


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_batch_writer_called_with_overwrite_pkeys_for_asset_allocation(_sleep):
    pipeline, _ = _make_pipeline(spider_type="asset_allocation", batch_n=1)
    item = {
        "year_month_day": "20260401",
        "asset_item_key": "nikko-user1-stocks",
        "asset_name": "日本株",
        "asset_type": "equity",
        "amount_value": 100000,
    }
    pipeline.process_item(item)
    pipeline.table.batch_writer.assert_called_once_with(
        overwrite_by_pkeys=["year_month_day", "asset_item_key"]
    )


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_batch_writer_called_without_overwrite_pkeys_for_unknown_spider_type(_sleep):
    """T6: unknown spider_type has no pkeys → batch_writer called with no kwargs."""
    pipeline, _ = _make_pipeline(spider_type="unknown_type", batch_n=1)
    pipeline.process_item(_make_transaction_item())
    pipeline.table.batch_writer.assert_called_once_with()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_batch_flush_raises_dropitem_on_dynamodb_error(_sleep):
    pipeline, _ = _make_pipeline(batch_n=1)
    pipeline.table.batch_writer.side_effect = RuntimeError("network error")

    with pytest.raises(DropItem):
        pipeline.process_item(_make_transaction_item())


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_batch_flush_error_increments_error_stat(_sleep):
    pipeline, _ = _make_pipeline(batch_n=1)
    pipeline.table.batch_writer.side_effect = RuntimeError("boom")

    with pytest.raises(DropItem):
        pipeline.process_item(_make_transaction_item())

    assert pipeline.crawler.stats.get_value("moneyforward/dynamodb/errors") == 1


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_sleep_called_even_on_error(mock_sleep):
    """H2: sleep must execute even when batch_writer raises."""
    pipeline, _ = _make_pipeline(batch_n=1, put_delay=5)
    pipeline.table.batch_writer.side_effect = RuntimeError("boom")

    with pytest.raises(DropItem):
        pipeline.process_item(_make_transaction_item())

    mock_sleep.assert_called_once_with(5)


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_buffer_cleared_before_batch_attempt(mock_sleep):
    """H1: snapshot pattern — buffer is empty after flush regardless of success/failure."""
    pipeline, _ = _make_pipeline(batch_n=2)
    pipeline.table.batch_writer.side_effect = RuntimeError("boom")

    pipeline._items = [_make_transaction_item("001"), _make_transaction_item("002")]

    with pytest.raises(DropItem):
        pipeline._batch_flush(is_force=True)

    # Buffer cleared before the AWS attempt — items are not re-queued on error
    assert pipeline._items == []


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_subsequent_items_not_contaminated_after_flush_error(mock_sleep):
    """T2: after a flush error (batch_n=1), next process_item starts a fresh batch."""
    pipeline, _ = _make_pipeline(batch_n=1)  # every item triggers flush
    pipeline.table.batch_writer.side_effect = RuntimeError("transient error")

    # First item → flush fails, buffer cleared via snapshot pattern
    with pytest.raises(DropItem):
        pipeline.process_item(_make_transaction_item("001"))

    assert pipeline._items == []

    # Restore to healthy mock; next item should start a clean batch of 1
    pipeline.table.batch_writer.side_effect = None
    fake_ctx2 = MagicMock()
    fake_batch2 = MagicMock()
    fake_ctx2.__enter__.return_value = fake_batch2
    fake_ctx2.__exit__.return_value = False
    pipeline.table.batch_writer.return_value = fake_ctx2

    next_item = _make_transaction_item("002")
    result = pipeline.process_item(next_item)
    # batch_n=1 → flushed immediately; PUT called with only the new item
    assert result is next_item
    assert fake_batch2.put_item.call_count == 1
    assert pipeline._items == []


# ---------------------------------------------------------------------------
# Scrapy hook signatures (no spider argument)
# ---------------------------------------------------------------------------


def test_open_spider_works_without_spider_argument():
    pipeline = DynamoDbPipeline(
        table_names={
            "transaction": "mf_transaction",
            "asset_allocation": "",
            "account": "",
        },
        put_delay=0,
        batch_n=10,
    )
    spider = MagicMock()
    spider.spider_type = "transaction"
    pipeline.crawler = MagicMock()
    pipeline.crawler.spider = spider

    mock_resource = MagicMock()
    mock_resource.Table.return_value = MagicMock()
    with patch(
        "moneyforward.pipelines.dynamodb.resolve_dynamodb_resource",
        return_value=mock_resource,
    ):
        pipeline.open_spider()

    assert pipeline.table is not None


@patch("moneyforward.pipelines.dynamodb.sleep", return_value=None)
def test_process_item_works_without_spider_argument(_sleep):
    pipeline, _ = _make_pipeline(batch_n=100)
    item = _make_transaction_item()
    result = pipeline.process_item(item)
    assert result is item


def test_close_spider_works_without_spider_argument():
    pipeline, _ = _make_pipeline(batch_n=10)
    pipeline.table = None
    pipeline.close_spider()


# ---------------------------------------------------------------------------
# _PKEYS completeness
# ---------------------------------------------------------------------------


def test_pkeys_covers_all_spider_types():
    assert set(_PKEYS.keys()) == {"transaction", "asset_allocation", "account"}
    for spider_type, keys in _PKEYS.items():
        assert len(keys) == 2, f"{spider_type} should have exactly 2 pkeys"


# ---------------------------------------------------------------------------
# resolve_dynamodb_resource
# ---------------------------------------------------------------------------


def test_resolve_dynamodb_resource_returns_injected_mock():
    from moneyforward.pipelines.dynamodb import resolve_dynamodb_resource

    mock = MagicMock()
    result = resolve_dynamodb_resource(dynamodb_resource=mock)
    assert result is mock


def test_resolve_dynamodb_resource_uses_resolver_for_credentials(monkeypatch):
    """Credentials are resolved via secrets resolver (env or Bitwarden backend)."""
    from moneyforward.pipelines.dynamodb import resolve_dynamodb_resource

    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")

    with (
        patch("moneyforward.pipelines.dynamodb._secrets_resolver") as mock_resolver,
        patch("boto3.resource") as mock_resource,
    ):
        mock_resolver.get.side_effect = lambda key: {
            "AWS_ACCESS_KEY_ID": "TESTKEY",
            "AWS_SECRET_ACCESS_KEY": "TESTSECRET",
        }[key]
        mock_resource.return_value = MagicMock()

        resolve_dynamodb_resource()

        mock_resource.assert_called_once_with(
            "dynamodb",
            aws_access_key_id="TESTKEY",
            aws_secret_access_key="TESTSECRET",
            region_name="ap-northeast-1",
        )


def test_resolve_dynamodb_resource_passes_none_when_secret_not_found(monkeypatch):
    """SecretNotFound → None → boto3 default credential chain."""
    from moneyforward.pipelines.dynamodb import resolve_dynamodb_resource
    from moneyforward.secrets.exceptions import SecretNotFound

    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    with (
        patch("moneyforward.pipelines.dynamodb._secrets_resolver") as mock_resolver,
        patch("boto3.resource") as mock_resource,
    ):
        mock_resolver.get.side_effect = SecretNotFound("not set")
        mock_resource.return_value = MagicMock()

        resolve_dynamodb_resource()

        mock_resource.assert_called_once_with(
            "dynamodb",
            aws_access_key_id=None,
            aws_secret_access_key=None,
            region_name=None,
        )


def test_resolve_dynamodb_resource_bitwarden_mode(monkeypatch):
    """Bitwarden backend: credentials come from BWS cache, not os.environ."""
    from moneyforward.pipelines.dynamodb import resolve_dynamodb_resource

    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")

    with (
        patch("moneyforward.pipelines.dynamodb._secrets_resolver") as mock_resolver,
        patch("boto3.resource") as mock_resource,
    ):
        mock_resolver.get.side_effect = lambda key: {
            "AWS_ACCESS_KEY_ID": "BWS_KEY",
            "AWS_SECRET_ACCESS_KEY": "BWS_SECRET",
        }[key]
        mock_resource.return_value = MagicMock()

        resolve_dynamodb_resource()

        mock_resource.assert_called_once_with(
            "dynamodb",
            aws_access_key_id="BWS_KEY",
            aws_secret_access_key="BWS_SECRET",
            region_name="ap-northeast-1",
        )
