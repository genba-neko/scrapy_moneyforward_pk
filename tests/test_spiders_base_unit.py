"""MoneyforwardBase: force-login wiring, errback, follow-up replay."""

from __future__ import annotations

import importlib
import logging
from typing import Any, cast
from unittest.mock import MagicMock

import scrapy
from scrapy.http import Request

from moneyforward_pk.spiders.base.moneyforward_base import MoneyforwardBase

_TEST_PASSWORD = "dummy-pass"  # noqa: S105 — fixture credential, not a real secret


class _StubSpider(MoneyforwardBase):
    name = "mf_test_base"


def _build_spider() -> _StubSpider:
    spider = _StubSpider(login_user="x@example.com", login_pass=_TEST_PASSWORD)
    crawler = MagicMock()
    crawler.stats = MagicMock()
    spider.crawler = crawler
    return spider


def _stats_mock(spider: _StubSpider) -> MagicMock:
    return cast(MagicMock, cast(Any, spider.crawler).stats)


def test_handle_force_login_strips_consumed_flag_and_carries_followup():
    """C1 fix: meta flag is consumed; original request becomes follow_up."""
    spider = _build_spider()
    retry = Request(
        url="https://moneyforward.com/cf",
        meta={"moneyforward_force_login": True, "login_retry_times": 1},
    )

    login_req = spider.handle_force_login(retry)

    assert isinstance(login_req, scrapy.Request)
    assert login_req.url == spider.start_url
    assert login_req.meta["moneyforward_follow_up"] is retry
    # The flag must be stripped so the follow-up does not loop back.
    assert "moneyforward_force_login" not in retry.meta
    # Stats counter must be bumped so operators can detect re-auth churn.
    _stats_mock(spider).inc_value.assert_called_with(
        f"{spider.name}/login/forced", count=1
    )


def test_errback_playwright_pops_page_meta():
    """errback must pop (not get) so managed_page cannot double-close."""
    spider = _build_spider()
    page = MagicMock()
    page.close = MagicMock(return_value=_NoopAwaitable())
    failed_request = Request(
        url="https://moneyforward.com/cf",
        meta={"playwright_page": page},
    )
    failure = MagicMock()
    failure.request = failed_request

    spider.errback_playwright(failure)

    assert "playwright_page" not in failed_request.meta
    _stats_mock(spider).inc_value.assert_any_call(
        f"{spider.name}/playwright/errback", count=1
    )


def test_errback_playwright_no_page_does_not_raise():
    """No-op errback path when the request never received a page handle."""
    spider = _build_spider()
    failed_request = Request(url="https://moneyforward.com/cf")
    failure = MagicMock()
    failure.request = failed_request

    spider.errback_playwright(failure)


def test_build_login_request_carries_follow_up():
    spider = _build_spider()
    follow_up = Request(url="https://moneyforward.com/cf")

    req = spider._build_login_request(follow_up=follow_up)

    assert req.meta["moneyforward_follow_up"] is follow_up
    assert req.callback == spider._parse_after_login
    assert req.errback == spider.errback_playwright


class _NoopAwaitable:
    """Stand-in for an awaited coroutine so MagicMock can be tested sync."""

    def close(self) -> None:
        return None

    def __await__(self):
        if False:  # pragma: no cover - never iterated in sync tests
            yield None
        return None


def test_base_module_import_does_not_configure_root_logger():
    """iter2 T2: importing the base spider must not mutate root logger state.

    setup_common_logging() used to fire at import time, which made the test
    suite's root logger configuration depend on import order. The call now
    lives inside ``from_crawler`` so library-style imports are side-effect-free.
    """
    flag = "_moneyforward_pk_logging_configured"
    root = logging.getLogger()
    if hasattr(root, flag):
        delattr(root, flag)

    # Re-import the module fresh to simulate a cold import.
    import moneyforward_pk.spiders.base.moneyforward_base as base_mod

    importlib.reload(base_mod)
    assert not getattr(root, flag, False)


def test_errback_playwright_uses_get_running_loop_outside_loop():
    """iter2 T2: sync test path (no running loop) closes coro instead of raising."""
    spider = _build_spider()

    class _CoroLike:
        closed = False

        def close(self) -> None:
            self.closed = True

    coro = _CoroLike()
    page = MagicMock()
    page.close = MagicMock(return_value=coro)
    failed_request = Request(
        url="https://moneyforward.com/cf",
        meta={"playwright_page": page},
    )
    failure = MagicMock()
    failure.request = failed_request

    spider.errback_playwright(failure)
    assert coro.closed is True
