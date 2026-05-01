"""MfTransactionSpider: month switcher path + after_login expansion."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import scrapy
from scrapy.http import HtmlResponse, Request, Response

from moneyforward_pk.spiders.transaction import MfTransactionSpider

_FIXTURE_HTML = (
    "<html><body><table><tbody class='transaction_list'>"
    "<tr class='target-active'>"
    "<td></td>"
    '<td class="date" data-table-sortable-value="2025/01/15-1"><span>01/15</span></td>'
    '<td class="content"><span>食料</span></td>'
    '<td class="amount"><span>-200</span></td>'
    '<td class="sub_account_id_hash"><span>cash</span></td>'
    '<td class="lctg"><a>食費</a></td>'
    '<td class="mctg"><a>食料品</a></td>'
    '<td class="memo"><span></span></td>'
    "</tr></tbody></table></body></html>"
)


def _mk_response(html: str, *, page: Any) -> HtmlResponse:
    request = Request(
        url="https://moneyforward.com/cf",
        meta={"playwright_page": page},
    )
    return HtmlResponse(
        url="https://moneyforward.com/cf",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=request,
    )


def _drive(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _collect(agen) -> list:
    return [x async for x in agen]


def test_after_login_emits_one_request_per_month():
    """past_months controls how many monthly requests after_login schedules."""
    spider = MfTransactionSpider(past_months=3)
    response = MagicMock(spec=Response)

    async def gather():
        return await _collect(spider.after_login(response))

    reqs = _drive(gather())
    assert len(reqs) == 3
    # Same target URL but distinct (year, month) cb_kwargs per request.
    months = {(r.cb_kwargs["year"], r.cb_kwargs["month"]) for r in reqs}
    assert len(months) == 3


def test_parse_month_returns_early_without_page():
    spider = MfTransactionSpider()
    response = Response(
        url="https://moneyforward.com/cf",
        request=Request(url="https://moneyforward.com/cf"),
    )

    async def gather():
        return await _collect(spider.parse_month(response, year=2025, month=1))

    assert _drive(gather()) == []


def _mk_visible_month_locator() -> MagicMock:
    """Return a Locator-like mock supporting wait_for + click."""
    locator = MagicMock()
    locator.wait_for = AsyncMock()
    locator.click = AsyncMock()
    return locator


def test_parse_month_yields_items_after_switcher_succeeds():
    """Happy path: month switcher clicks succeed and items are yielded."""
    spider = MfTransactionSpider()
    crawler = MagicMock()
    crawler.stats = MagicMock()
    spider.crawler = crawler

    page = MagicMock()
    page.wait_for_load_state = AsyncMock()
    page.click = AsyncMock()
    page.locator = MagicMock(return_value=_mk_visible_month_locator())
    page.content = AsyncMock(return_value=_FIXTURE_HTML)
    response = _mk_response(_FIXTURE_HTML, page=page)

    async def gather():
        return await _collect(spider.parse_month(response, year=2025, month=1))

    items = _drive(gather())
    assert len(items) == 1
    assert items[0]["amount_number"] == -200
    assert items[0]["year_month"] == "202501"
    crawler.stats.inc_value.assert_any_call(f"{spider.name}/records", count=1)
    page.locator.assert_called_once_with('li[data-year="2025"][data-month="1"]:visible')


def test_parse_month_aborts_when_switcher_throws():
    """A click failure must abort the month, bump months_failed, no items."""
    spider = MfTransactionSpider()
    crawler = MagicMock()
    crawler.stats = MagicMock()
    spider.crawler = crawler

    page = MagicMock()
    page.wait_for_load_state = AsyncMock()
    page.click = AsyncMock(side_effect=RuntimeError("month-switcher down"))
    page.locator = MagicMock(return_value=_mk_visible_month_locator())
    page.content = AsyncMock(return_value=_FIXTURE_HTML)
    response = _mk_response(_FIXTURE_HTML, page=page)

    async def gather():
        return await _collect(spider.parse_month(response, year=2025, month=1))

    assert _drive(gather()) == []
    # records counter must not be bumped when the month was skipped.
    inc_keys = [c.args[0] for c in crawler.stats.inc_value.call_args_list]
    assert f"{spider.name}/records" not in inc_keys
    # months_failed counter must be bumped so summary classifies as partial.
    crawler.stats.inc_value.assert_any_call(f"{spider.name}/months_failed", count=1)


def test_parse_month_aborts_when_visible_month_locator_times_out():
    """If the :visible month li never appears, abort + bump months_failed."""
    spider = MfTransactionSpider()
    crawler = MagicMock()
    crawler.stats = MagicMock()
    spider.crawler = crawler

    locator = MagicMock()
    locator.wait_for = AsyncMock(side_effect=RuntimeError("Timeout 10000ms"))
    locator.click = AsyncMock()

    page = MagicMock()
    page.wait_for_load_state = AsyncMock()
    page.click = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    page.content = AsyncMock(return_value=_FIXTURE_HTML)
    response = _mk_response(_FIXTURE_HTML, page=page)

    async def gather():
        return await _collect(spider.parse_month(response, year=2025, month=10))

    assert _drive(gather()) == []
    locator.click.assert_not_called()
    crawler.stats.inc_value.assert_any_call(f"{spider.name}/months_failed", count=1)


def test_from_crawler_pulls_past_months_from_settings():
    spider = MfTransactionSpider()
    assert spider.past_months is None

    crawler = MagicMock()
    crawler.settings.getint.return_value = 6
    crawler.settings.get.return_value = ""
    spider2 = MfTransactionSpider.from_crawler(crawler)
    assert spider2.past_months == 6


def test_after_login_today_default():
    """A bare past_months=1 collapses to a single year/month."""
    spider = MfTransactionSpider(past_months=1)
    response = MagicMock(spec=Response)

    async def gather():
        return await _collect(spider.after_login(response))

    reqs = _drive(gather())
    assert len(reqs) == 1
    today = date.today()
    assert reqs[0].cb_kwargs == {"year": today.year, "month": today.month}
    assert isinstance(reqs[0], scrapy.Request)
