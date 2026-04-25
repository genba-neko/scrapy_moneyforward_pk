"""Downloader middleware that retries on detected login-expiry.

If a Playwright response lands on a login page, re-issue the same request with
a bumped ``login_retry_times`` counter. The base spider is responsible for
re-logging in on the next cycle (Playwright context reuse keeps cookies, so a
bounce normally means the session truly expired).
"""

from __future__ import annotations

import logging

from scrapy import Request

from moneyforward_pk.utils.session_utils import is_session_expired

logger = logging.getLogger(__name__)


class PlaywrightSessionMiddleware:
    """Detect session expiry and retry up to ``login_max_retry`` times."""

    def __init__(self, login_max_retry: int = 2) -> None:
        self.login_max_retry = login_max_retry

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            login_max_retry=crawler.settings.getint("MONEYFORWARD_LOGIN_MAX_RETRY", 2),
        )

    def process_response(self, request: Request, response, spider):
        if not request.meta.get("playwright"):
            return response
        if not is_session_expired(response):
            return response

        attempts = int(request.meta.get("login_retry_times", 0))
        if attempts >= self.login_max_retry:
            spider.logger.error(
                "Session expiry persists after %d retries: %s", attempts, response.url
            )
            spider.crawler.stats.inc_value(f"{spider.name}/session/expired_final")
            return response

        spider.logger.warning(
            "Session expired, retrying (%d/%d): %s",
            attempts + 1,
            self.login_max_retry,
            request.url,
        )
        spider.crawler.stats.inc_value(f"{spider.name}/session/retry")

        new_request = request.copy()
        new_request.dont_filter = True
        new_request.meta["login_retry_times"] = attempts + 1
        new_request.meta["moneyforward_force_login"] = True
        return new_request
