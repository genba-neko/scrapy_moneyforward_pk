"""Downloader middleware that retries on detected login-expiry.

If a Playwright response lands on a login page, route the request through the
base spider's ``handle_force_login`` hook so the next download flushes any
stale session and replays the login flow before retrying the original URL.
"""

from __future__ import annotations

import logging
from typing import Any

from scrapy import Request
from scrapy.exceptions import IgnoreRequest

from moneyforward.utils.session_utils import is_session_expired

logger = logging.getLogger(__name__)


class PlaywrightSessionMiddleware:
    """Detect session expiry and retry up to ``login_max_retry`` times."""

    crawler: Any  # set by from_crawler()

    def __init__(self, login_max_retry: int = 2) -> None:
        self.login_max_retry = login_max_retry

    @classmethod
    def from_crawler(cls, crawler):
        instance = cls(
            login_max_retry=crawler.settings.getint("MONEYFORWARD_LOGIN_MAX_RETRY", 2),
        )
        instance.crawler = crawler
        return instance

    def process_response(self, request: Request, response):
        if not request.meta.get("playwright"):
            return response
        if not is_session_expired(response):
            return response

        spider = self.crawler.spider
        attempts = int(request.meta.get("login_retry_times", 0))
        if attempts >= self.login_max_retry:
            spider.logger.error(
                "Session expiry persists after %d retries: %s", attempts, response.url
            )
            spider.crawler.stats.inc_value(f"{spider.name}/session/expired_final")
            # Opus M2: drop the request rather than passing the login-page
            # response down to the spider as if it were valid content. The
            # ``expired_final`` counter is read by crawl_runner._classify_result
            # to mark this spider invocation as ``failed: SessionExpired``.
            raise IgnoreRequest(
                f"session expiry retry limit exceeded ({attempts}/{self.login_max_retry})"
            )

        spider.logger.warning(
            "Session expired, retrying (%d/%d): %s",
            attempts + 1,
            self.login_max_retry,
            request.url,
        )
        spider.crawler.stats.inc_value(f"{spider.name}/session/retry")

        # Issue #43: drop the on-disk storage_state so the retry request
        # does not get the same stale cookies injected by
        # ``_build_login_request``. Without this, a permanently-invalid
        # session file would loop ``expired → retry → expired`` forever.
        session_manager = getattr(spider, "session_manager", None)
        if session_manager is not None:
            session_manager.invalidate_session()

        new_request = request.copy()
        new_request.dont_filter = True
        # Drop stale Playwright handles inherited from request.copy(): the
        # original page was already consumed/closed when the response landed,
        # so reusing it would double-close via managed_page (defect C2).
        new_request.meta.pop("playwright_page", None)
        new_request.meta.pop("playwright_page_methods", None)
        # Also drop the storage_state injection from the original request so
        # the retry doesn't carry the just-invalidated session cookies.
        new_request.meta.pop("playwright_context_kwargs", None)
        new_request.meta["login_retry_times"] = attempts + 1
        new_request.meta["moneyforward_force_login"] = True

        # Defect C1 fix: hand the retry to the spider so it can prepend a
        # fresh login flow. Falls back to a plain retry if the spider does
        # not implement the hook (non-MoneyforwardBase spiders).
        handler = getattr(spider, "handle_force_login", None)
        if callable(handler):
            return handler(new_request)
        return new_request
