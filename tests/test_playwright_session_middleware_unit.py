"""PlaywrightSessionMiddleware: retry on session-expiry."""

from __future__ import annotations

from unittest.mock import MagicMock

from scrapy.http import HtmlResponse, Request

from moneyforward_pk.middlewares.playwright_session import (
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


def test_passes_through_non_playwright_requests():
    mw = PlaywrightSessionMiddleware(login_max_retry=2)
    req = Request(url="https://example.com/")
    resp = HtmlResponse(url=req.url, body=b"ok", request=req)
    assert mw.process_response(req, resp, _spider({})) is resp


def test_passes_through_healthy_response():
    mw = PlaywrightSessionMiddleware(login_max_retry=2)
    req = _request()
    resp = HtmlResponse(
        url="https://moneyforward.com/cf",
        body="<html><head><title>家計簿</title></head></html>".encode("utf-8"),
        request=req,
    )
    assert mw.process_response(req, resp, _spider({})) is resp


def test_retries_on_login_url():
    mw = PlaywrightSessionMiddleware(login_max_retry=2)
    stats: dict = {}
    req = _request()
    resp = HtmlResponse(
        url="https://moneyforward.com/sign_in",
        body="<html><head><title>ログイン</title></head></html>".encode("utf-8"),
        request=req,
    )
    out = mw.process_response(req, resp, _spider(stats))
    assert isinstance(out, Request)
    assert out.meta["login_retry_times"] == 1
    assert out.meta["moneyforward_force_login"] is True
    assert stats["mf_test/session/retry"] == 1


def test_stops_after_max_retry():
    mw = PlaywrightSessionMiddleware(login_max_retry=1)
    stats: dict = {}
    req = _request(attempts=1)
    resp = HtmlResponse(
        url="https://moneyforward.com/sign_in",
        body=b"<html></html>",
        request=req,
    )
    out = mw.process_response(req, resp, _spider(stats))
    assert out is resp
    assert stats["mf_test/session/expired_final"] == 1
