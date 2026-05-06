"""PlaywrightSessionMiddleware: retry on session-expiry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from scrapy.http import HtmlResponse, Request

from moneyforward.middlewares.playwright_session import (
    PlaywrightSessionMiddleware,
)


def _spider(stats: dict):
    s = MagicMock()
    s.name = "mf_test"
    s.logger = MagicMock()
    s.crawler.stats.inc_value = lambda k, count=1, **_: stats.__setitem__(
        k, stats.get(k, 0) + count
    )
    return s


def _request(url="https://moneyforward.com/cf", attempts=0):
    req = Request(url=url, meta={"playwright": True, "login_retry_times": attempts})
    return req


def _mw(spider, login_max_retry: int = 2) -> PlaywrightSessionMiddleware:
    mw = PlaywrightSessionMiddleware(login_max_retry=login_max_retry)
    mw.crawler = MagicMock()
    mw.crawler.spider = spider
    return mw


def test_passes_through_non_playwright_requests():
    spider = _spider({})
    mw = _mw(spider)
    req = Request(url="https://example.com/")
    resp = HtmlResponse(url=req.url, body=b"ok", request=req)
    assert mw.process_response(req, resp) is resp


def test_passes_through_healthy_response():
    spider = _spider({})
    mw = _mw(spider)
    req = _request()
    resp = HtmlResponse(
        url="https://moneyforward.com/cf",
        body="<html><head><title>家計簿</title></head></html>".encode("utf-8"),
        request=req,
    )
    assert mw.process_response(req, resp) is resp


def test_retries_on_login_url():
    stats: dict = {}
    spider = _spider(stats)
    mw = _mw(spider)
    # Spider lacks handle_force_login → middleware returns the plain retry.
    spider.handle_force_login = None
    req = _request()
    resp = HtmlResponse(
        url="https://moneyforward.com/sign_in",
        body="<html><head><title>ログイン</title></head></html>".encode("utf-8"),
        request=req,
    )
    out = mw.process_response(req, resp)
    assert isinstance(out, Request)
    assert out.meta["login_retry_times"] == 1
    assert out.meta["moneyforward_force_login"] is True
    assert stats["mf_test/session/retry"] == 1


def test_retry_drops_stale_playwright_page_meta():
    """Defect C2: request.copy() must not leak the closed page handle."""
    spider = _spider({})
    mw = _mw(spider)
    stale_page = MagicMock(name="closed_page")
    req = Request(
        url="https://moneyforward.com/cf",
        meta={
            "playwright": True,
            "playwright_page": stale_page,
            "playwright_page_methods": ["m1", "m2"],
            "login_retry_times": 0,
        },
    )
    resp = HtmlResponse(
        url="https://moneyforward.com/sign_in",
        body=b"<html></html>",
        request=req,
    )
    spider.handle_force_login = None
    out = mw.process_response(req, resp)
    assert isinstance(out, Request)
    assert "playwright_page" not in out.meta
    assert "playwright_page_methods" not in out.meta


def test_retry_invokes_handle_force_login():
    """Defect C1: middleware delegates to spider.handle_force_login when present."""
    spider = _spider({})
    mw = _mw(spider)
    sentinel = Request(url="https://moneyforward.com/login")
    spider.handle_force_login = MagicMock(return_value=sentinel)

    req = _request()
    resp = HtmlResponse(
        url="https://moneyforward.com/sign_in",
        body=b"<html></html>",
        request=req,
    )
    out = mw.process_response(req, resp)
    assert out is sentinel
    spider.handle_force_login.assert_called_once()
    forwarded = spider.handle_force_login.call_args.args[0]
    assert forwarded.meta["moneyforward_force_login"] is True


def test_stops_after_max_retry():
    """Issue #40 / Opus M2: at retry limit the middleware raises IgnoreRequest
    so the spider does not see the bad login-page response as content. The
    ``expired_final`` counter is what crawl_runner reads to mark the spider
    invocation as ``failed: SessionExpired``."""
    from scrapy.exceptions import IgnoreRequest

    stats: dict = {}
    spider = _spider(stats)
    mw = _mw(spider, login_max_retry=1)
    req = _request(attempts=1)
    resp = HtmlResponse(
        url="https://moneyforward.com/sign_in",
        body=b"<html></html>",
        request=req,
    )
    with pytest.raises(IgnoreRequest):
        mw.process_response(req, resp)
    assert stats["mf_test/session/expired_final"] == 1


def test_from_crawler_uses_settings_login_max_retry():
    """from_crawler reads MONEYFORWARD_LOGIN_MAX_RETRY (default 2)."""
    crawler = MagicMock()
    crawler.settings.getint.return_value = 5
    mw = PlaywrightSessionMiddleware.from_crawler(crawler)
    assert mw.login_max_retry == 5
    crawler.settings.getint.assert_called_with("MONEYFORWARD_LOGIN_MAX_RETRY", 2)


def test_session_expiry_retry_invalidates_session_state():
    """Issue #43: middleware must drop on-disk storage_state before retry."""
    stats: dict = {}
    spider = _spider(stats)
    mw = _mw(spider)
    spider.session_manager = MagicMock()
    spider.handle_force_login = MagicMock(side_effect=lambda r: r)
    req = _request(attempts=0)
    # Add a stored storage_state to confirm it gets stripped from the retry.
    req.meta["playwright_context_kwargs"] = {"storage_state": "/tmp/stale.json"}
    resp = HtmlResponse(
        url="https://moneyforward.com/sign_in",
        body=b"<html></html>",
        request=req,
    )
    out = mw.process_response(req, resp)
    spider.session_manager.invalidate_session.assert_called_once()
    # The retry request must not carry the stale storage_state.
    assert isinstance(out, Request)
    assert "playwright_context_kwargs" not in out.meta


def test_retry_final_does_not_invoke_handle_force_login():
    """When attempts >= max, the middleware must NOT route to handle_force_login;
    instead it raises IgnoreRequest (Issue #40 / Opus M2)."""
    from scrapy.exceptions import IgnoreRequest

    spider = _spider({})
    mw = _mw(spider, login_max_retry=1)
    spider.handle_force_login = MagicMock()
    req = _request(attempts=1)
    resp = HtmlResponse(
        url="https://moneyforward.com/sign_in",
        body=b"<html></html>",
        request=req,
    )
    with pytest.raises(IgnoreRequest):
        mw.process_response(req, resp)
    spider.handle_force_login.assert_not_called()
