"""Slack notification extension hooked to ``spider_closed``.

The extension is opt-in: when ``SLACK_INCOMING_WEBHOOK_URL`` is empty (the
default in tests and CI), the extension installs itself but performs no
network calls.
"""

from __future__ import annotations

import logging

from scrapy import signals
from scrapy.exceptions import NotConfigured

from moneyforward_pk.utils.slack_notifier import SlackNotifier

logger = logging.getLogger(__name__)


class SlackNotifierExtension:
    """Send a one-line Slack summary when a spider finishes.

    Notes
    -----
    The summary includes spider name, finish reason, item count, and elapsed
    seconds when those stats are available. Network failures are swallowed
    inside ``SlackNotifier.notify`` so a stuck Slack endpoint cannot fail
    the crawl.
    """

    def __init__(self, webhook_url: str) -> None:
        self.notifier = SlackNotifier(webhook_url=webhook_url)

    @classmethod
    def from_crawler(cls, crawler) -> "SlackNotifierExtension":
        """Wire the extension to ``spider_closed`` if a webhook is configured."""
        webhook = crawler.settings.get("SLACK_INCOMING_WEBHOOK_URL", "") or ""
        if not webhook:
            # Disabled: Scrapy will skip loading the extension entirely so we
            # do not waste a signal subscription on a dormant notifier.
            raise NotConfigured("SLACK_INCOMING_WEBHOOK_URL not set")
        ext = cls(webhook_url=webhook)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_closed(self, spider, reason: str) -> None:
        """Build a short summary and forward it to Slack."""
        stats = getattr(getattr(spider, "crawler", None), "stats", None)
        item_count = 0
        elapsed: float | None = None
        if stats is not None:
            try:
                item_count = int(stats.get_value("item_scraped_count", 0) or 0)
                elapsed_value = stats.get_value("elapsed_time_seconds")
                if elapsed_value is not None:
                    elapsed = float(elapsed_value)
            except (TypeError, ValueError):
                pass

        elapsed_text = f" elapsed={elapsed:.1f}s" if elapsed is not None else ""
        text = (
            f"[moneyforward_pk] {spider.name} closed reason={reason} "
            f"items={item_count}{elapsed_text}"
        )
        try:
            self.notifier.notify(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Slack notify failed: %s", exc)
