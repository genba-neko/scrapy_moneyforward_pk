"""MoneyforwardBase: force-login wiring, errback, follow-up replay."""

from __future__ import annotations

import asyncio
import importlib
import logging
from typing import Any, cast
from unittest.mock import MagicMock

import scrapy
from scrapy.http import Request, Response

from moneyforward.spiders.base.moneyforward_base import MoneyforwardBase

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
    page.unroute = MagicMock(return_value=_NoopAwaitable())
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
    flag = "_moneyforward_logging_configured"
    root = logging.getLogger()
    if hasattr(root, flag):
        delattr(root, flag)

    # Re-import the module fresh to simulate a cold import.
    import moneyforward.spiders.base.moneyforward_base as base_mod

    importlib.reload(base_mod)
    assert not getattr(root, flag, False)


def _drive(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _collect(agen) -> list:
    return [x async for x in agen]


def test_start_emits_login_request():
    """The async start() entry point must emit exactly one login request."""
    spider = _build_spider()

    async def gather():
        return await _collect(spider.start())

    reqs = _drive(gather())
    assert len(reqs) == 1
    assert reqs[0].url == spider.start_url


def test_start_requests_back_compat_yields_login_request():
    """start_requests must remain functional for older Scrapy callers."""
    spider = _build_spider()
    reqs = list(spider.start_requests())
    assert len(reqs) == 1
    assert reqs[0].callback == spider._parse_after_login


def test_iter_after_login_sync_path_yields_items():
    """When after_login returns a plain iterable, _iter_after_login forwards it."""
    spider = _build_spider()

    def sync_after_login(_response):
        return iter(["a", "b"])

    spider.after_login = sync_after_login  # type: ignore[method-assign]

    response = Response(
        url="https://moneyforward.com/",
        request=Request(url="https://moneyforward.com/"),
    )

    async def gather():
        return await _collect(spider._iter_after_login(response))

    assert _drive(gather()) == ["a", "b"]


def test_iter_after_login_async_path_yields_items():
    """When after_login returns an async iterator, _iter_after_login bridges it."""
    spider = _build_spider()

    async def async_after_login(_response):
        for item in ["x", "y"]:
            yield item

    spider.after_login = async_after_login  # type: ignore[method-assign]
    response = Response(
        url="https://moneyforward.com/",
        request=Request(url="https://moneyforward.com/"),
    )

    async def gather():
        return await _collect(spider._iter_after_login(response))

    assert _drive(gather()) == ["x", "y"]


def test_iter_after_login_handles_none_return():
    """A subclass that returns None from after_login must terminate cleanly."""
    spider = _build_spider()
    spider.after_login = lambda _response: None  # type: ignore[method-assign]
    response = Response(
        url="https://moneyforward.com/",
        request=Request(url="https://moneyforward.com/"),
    )

    async def gather():
        return await _collect(spider._iter_after_login(response))

    assert _drive(gather()) == []


def test_errback_playwright_uses_get_running_loop_outside_loop():
    """iter2 T2 / iter3 T2: sync test path (no running loop) closes the
    teardown coroutine instead of raising. After unifying on
    ``close_page_quietly`` the helper coroutine is the one we close;
    asserting no exception leaks is the contract."""
    spider = _build_spider()
    page = MagicMock()
    page.unroute = MagicMock(return_value=_NoopAwaitable())
    page.close = MagicMock(return_value=_NoopAwaitable())
    failed_request = Request(
        url="https://moneyforward.com/cf",
        meta={"playwright_page": page},
    )
    failure = MagicMock()
    failure.request = failed_request

    # Must not raise even though no event loop is running.
    spider.errback_playwright(failure)
    assert "playwright_page" not in failed_request.meta


def test_parse_after_login_missing_page_logs_and_returns():
    """When playwright_page is absent the callback must short-circuit."""
    spider = _build_spider()
    response = Response(
        url="https://moneyforward.com/",
        request=Request(url="https://moneyforward.com/"),
    )

    # _parse_after_login is now a coroutine returning a list (not async gen).
    async def gather():
        return await spider._parse_after_login(response)

    result = _drive(gather())
    assert result == []


# test_parse_after_login_passes_login_attempt_to_login_flow was removed
# along with the alt-as-retry feature (Issue #40 / PR consolidation).


class _ValueAwaitable:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        if False:  # pragma: no cover
            yield None
        return self.value


def _value_awaitable(value):
    return _ValueAwaitable(value)


def test_after_login_default_returns_empty_iterator():
    """Base ``after_login`` is a no-op; subclasses must override."""
    spider = _build_spider()
    response = Response(
        url="https://moneyforward.com/",
        request=Request(url="https://moneyforward.com/"),
    )
    assert list(spider.after_login(response)) == []
