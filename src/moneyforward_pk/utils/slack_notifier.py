"""Slack notification helper. No-op when webhook URL is unset."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url or os.environ.get(
            "SLACK_INCOMING_WEBHOOK_URL", ""
        )

    def notify(self, text: str) -> None:
        if not self.webhook_url:
            logger.debug("Slack webhook unset; skip notify: %s", text)
            return
        try:
            import slackweb

            slackweb.Slack(url=self.webhook_url).notify(text=text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Slack notify failed: %s", exc)
