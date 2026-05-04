"""MfAssetAllocationSpider: portfolio fetch + item yield."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import scrapy
from scrapy.http import HtmlResponse, Request, Response

from moneyforward.spiders.asset_allocation import MfAssetAllocationSpider

_PORTFOLIO_HTML = (
    "<html><body><table>"
    '<tr><th><a href="#portfolio_det_depo">預金</a></th><td>10,000円</td></tr>'
    '<tr><th><a href="#portfolio_det_mf">投資</a></th><td>2,000円</td></tr>'
    "</table></body></html>"
)


def _mk_response(html: str, *, page: Any) -> HtmlResponse:
    request = Request(
        url="https://moneyforward.com/bs/portfolio",
        meta={"playwright_page": page},
    )
    return HtmlResponse(
        url="https://moneyforward.com/bs/portfolio",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=request,
    )


def _drive(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _collect(agen) -> list:
    return [x async for x in agen]


def test_after_login_yields_portfolio_request():
    spider = MfAssetAllocationSpider()
    response = MagicMock(spec=Response)

    async def gather():
        return await _collect(spider.after_login(response))

    reqs = _drive(gather())
    assert len(reqs) == 1
    assert isinstance(reqs[0], scrapy.Request)
    assert reqs[0].url == "https://moneyforward.com/bs/portfolio"


def test_parse_portfolio_returns_early_without_page():
    spider = MfAssetAllocationSpider()
    response = Response(
        url="https://moneyforward.com/bs/portfolio",
        request=Request(url="https://moneyforward.com/bs/portfolio"),
    )

    async def gather():
        return await _collect(spider.parse_portfolio(response))

    assert _drive(gather()) == []


def test_parse_portfolio_yields_items():
    spider = MfAssetAllocationSpider(login_user="u@example.com")
    crawler = MagicMock()
    crawler.stats = MagicMock()
    spider.crawler = crawler

    page = MagicMock()
    page.content = AsyncMock(return_value=_PORTFOLIO_HTML)
    response = _mk_response(_PORTFOLIO_HTML, page=page)

    async def gather():
        return await _collect(spider.parse_portfolio(response))

    items = _drive(gather())
    assert len(items) == 2
    types = [it["asset_type"] for it in items]
    assert types == ["portfolio_det_depo", "portfolio_det_mf"]
    crawler.stats.inc_value.assert_any_call(f"{spider.name}/records", count=2)
