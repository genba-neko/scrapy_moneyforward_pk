"""SlackNotifierExtension: ``spider_closed`` wiring + no-op fallback."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from scrapy import signals
from scrapy.exceptions import NotConfigured

from moneyforward.extensions.slack_notifier_extension import (
    SlackNotifierExtension,
)


def _make_crawler() -> MagicMock:
    crawler = MagicMock()
    crawler.signals.connect = MagicMock()
    return crawler


def test_extension_is_not_configured_when_webhook_is_empty(monkeypatch):
    """Disabled by default: empty webhook must raise NotConfigured."""
    monkeypatch.setenv("SLACK_INCOMING_WEBHOOK_URL", "")
    with pytest.raises(NotConfigured):
        SlackNotifierExtension.from_crawler(_make_crawler())


def test_extension_is_not_configured_when_webhook_is_missing(monkeypatch):
    # SLACK_INCOMING_WEBHOOK_URL は conftest autouse fixture で削除済み
    with pytest.raises(NotConfigured):
        SlackNotifierExtension.from_crawler(_make_crawler())


def test_extension_connects_spider_closed_when_webhook_set(monkeypatch):
    monkeypatch.setenv(
        "SLACK_INCOMING_WEBHOOK_URL", "https://hooks.slack.com/services/x/y/z"
    )
    crawler = _make_crawler()
    ext = SlackNotifierExtension.from_crawler(crawler)
    assert isinstance(ext, SlackNotifierExtension)
    crawler.signals.connect.assert_called_once()
    args, kwargs = crawler.signals.connect.call_args
    assert kwargs.get("signal") is signals.spider_closed


def test_spider_closed_swallows_notify_failure():
    """A wedged Slack endpoint must not surface as a crawl failure."""
    ext = SlackNotifierExtension(webhook_url="https://hooks.slack.com/x/y/z")
    ext.notifier = MagicMock()
    ext.notifier.notify.side_effect = RuntimeError("network down")

    spider = MagicMock()
    spider.name = "mf_test"
    spider.crawler.stats.get_value.side_effect = lambda key, default=None: {
        "item_scraped_count": 3
    }.get(key, default)

    # Must not raise.
    ext.spider_closed(spider, reason="finished")
    ext.notifier.notify.assert_called_once()


def test_spider_closed_passes_summary_text():
    ext = SlackNotifierExtension(webhook_url="https://hooks.slack.com/x/y/z")
    ext.notifier = MagicMock()

    spider = MagicMock()
    spider.name = "mf_account"
    spider.crawler.stats.get_value.side_effect = lambda key, default=None: {
        "item_scraped_count": 9,
        "elapsed_time_seconds": 12.5,
    }.get(key, default)

    ext.spider_closed(spider, reason="finished")
    args, _ = ext.notifier.notify.call_args
    text = args[0]
    assert "mf_account" in text
    assert "items=9" in text
    assert "reason=finished" in text
    assert "elapsed=12.5s" in text
