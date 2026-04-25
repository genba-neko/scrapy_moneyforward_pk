"""MfAccountSpider: polling state machine + after_login wiring."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import scrapy
from scrapy.http import HtmlResponse, Request, Response

from moneyforward_pk.spiders.account import MfAccountSpider

_ONE_ROW_HTML = (
    "<html><body><table>"
    "<tr><th>金融機関</th><th>残高</th><th>更新日</th><th>ステータス</th></tr>"
    "<tr><td>テスト銀行</td><td>10,000円</td><td>2025/01/15</td>"
    '<td><span id="js-status-sentence-span-1">正常</span></td></tr>'
    "</table></body></html>"
)


def _mk_response(html: str, *, page: Any) -> HtmlResponse:
    """Build a Scrapy HtmlResponse carrying the playwright_page handle."""
    body = html.encode("utf-8")
    request = Request(
        url="https://moneyforward.com/accounts",
        meta={"playwright_page": page},
    )
    return HtmlResponse(
        url="https://moneyforward.com/accounts",
        body=body,
        encoding="utf-8",
        request=request,
    )


def _drive(coro):
    """Drive an async coroutine on a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


async def _collect(agen) -> list:
    out = []
    async for value in agen:
        out.append(value)
    return out


def test_after_login_yields_initial_accounts_request():
    """After-login emits a Playwright Request to /accounts with is_update=True."""
    spider = MfAccountSpider()
    response = MagicMock(spec=Response)

    async def gather():
        return await _collect(spider.after_login(response))

    requests = _drive(gather())
    assert len(requests) == 1
    req = requests[0]
    assert isinstance(req, scrapy.Request)
    assert req.url == "https://moneyforward.com/accounts"
    assert req.cb_kwargs == {"is_update": True, "attempt": 0}
    assert "playwright" in req.meta


def test_parse_accounts_page_returns_early_when_no_page():
    """Defensive guard: a request without a playwright_page yields nothing."""
    spider = MfAccountSpider()
    response = Response(
        url="https://moneyforward.com/accounts",
        request=Request(url="https://moneyforward.com/accounts"),
    )

    async def gather():
        return await _collect(
            spider.parse_accounts_page(response, is_update=False, attempt=0)
        )

    assert _drive(gather()) == []


def test_parse_accounts_page_yields_items_when_done():
    """is_updating=False path yields parsed account items."""
    spider = MfAccountSpider()
    crawler = MagicMock()
    crawler.stats = MagicMock()
    spider.crawler = crawler

    page = MagicMock()
    page.content = AsyncMock(return_value=_ONE_ROW_HTML)
    response = _mk_response(_ONE_ROW_HTML, page=page)

    async def gather():
        return await _collect(
            spider.parse_accounts_page(response, is_update=False, attempt=0)
        )

    items = _drive(gather())
    assert len(items) == 1
    assert items[0]["account_name"] == "テスト銀行"
    crawler.stats.inc_value.assert_any_call(f"{spider.name}/records", count=1)


def test_parse_accounts_page_retries_when_updating(monkeypatch):
    """is_updating=True schedules a follow-up retry request and skips items."""
    spider = MfAccountSpider()
    crawler = MagicMock()
    crawler.stats = MagicMock()
    spider.crawler = crawler
    spider.update_wait_seconds = 0  # avoid real sleep
    spider.update_max_retry = 3

    updating_html = (
        "<html><body><table>"
        "<tr><th>金融機関</th><th>残高</th><th>更新日</th><th>ステータス</th></tr>"
        "<tr><td>更新中銀行</td><td>1円</td><td>2025/01/15</td>"
        '<td><span id="js-status-sentence-span-1">更新中</span></td></tr>'
        "</table></body></html>"
    )
    page = MagicMock()
    page.content = AsyncMock(return_value=updating_html)
    response = _mk_response(updating_html, page=page)

    async def fake_sleep(*_a, **_kw):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def gather():
        return await _collect(
            spider.parse_accounts_page(response, is_update=False, attempt=0)
        )

    yielded = _drive(gather())
    # Updating path yields exactly one follow-up request (attempt=1) and no items.
    assert len(yielded) == 1
    assert isinstance(yielded[0], scrapy.Request)
    assert yielded[0].cb_kwargs == {"is_update": False, "attempt": 1}


def test_click_update_buttons_handles_count_failure():
    """Locator failures must downgrade to a warning, not crash the spider."""
    spider = MfAccountSpider()
    page = MagicMock()
    locator = MagicMock()
    locator.count = AsyncMock(side_effect=RuntimeError("locator broken"))
    page.locator.return_value = locator

    async def go():
        await spider._click_update_buttons(page)

    # Must not raise.
    _drive(go())
