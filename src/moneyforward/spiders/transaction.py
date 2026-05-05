"""Transaction spider (/cf monthly pages)."""

from __future__ import annotations

from datetime import date
from typing import AsyncIterator
from urllib.parse import urlparse

import scrapy
from dateutil.relativedelta import relativedelta
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from moneyforward.spiders._parsers import parse_transactions
from moneyforward.spiders.base.moneyforward_base import MoneyforwardBase
from moneyforward.utils.playwright_utils import (
    build_playwright_meta,
    managed_page,
)


class MfTransactionSpider(MoneyforwardBase):
    """Fetch past-N-months transactions.

    ``past_months`` controls the depth (default from ``SITE_PAST_MONTHS``).
    """

    name = "transaction"
    spider_type = "transaction"
    variant_name = "mf"  # default; overridden via ``site`` kwarg

    def __init__(self, *args, past_months: int | str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.past_months = int(past_months) if past_months is not None else None
        # variant の base_url から allowed_domains を動的決定 (派生サイト対応).
        self.allowed_domains = [urlparse(self.variant.base_url).netloc]

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider.past_months is None:
            spider.past_months = crawler.settings.getint("SITE_PAST_MONTHS", 12)
        return spider

    async def after_login(self, response: Response) -> AsyncIterator[scrapy.Request]:  # type: ignore[override]
        today = date.today()
        months = self.past_months if self.past_months is not None else 12
        for offset in range(months):
            target = today - relativedelta(months=offset)
            yield self._month_request(target.year, target.month)

    def _month_request(self, year: int, month: int) -> scrapy.Request:
        return scrapy.Request(
            url=self.variant.transactions_url,
            callback=self.parse_month,
            errback=self.errback_playwright,
            cb_kwargs={"year": year, "month": month},
            dont_filter=True,
            meta=build_playwright_meta(
                include_page=True,
                page_methods=[
                    PageMethod("wait_for_load_state", "domcontentloaded"),
                ],
            ),
        )

    async def parse_month(self, response: Response, year: int, month: int):
        page = response.meta.get("playwright_page")
        if page is None:
            return

        async with managed_page(page) as p:
            await p.wait_for_load_state("domcontentloaded")
            try:
                await p.click(".fc-button-selectMonth", timeout=30_000)
                await p.click(f'li[data-year="{year}"]', timeout=30_000)
                # 年クリック → 月一覧再描画の完了を offsetParent で確認 (DOM 安定化)。
                # E2E 観測 (2026-05-02): scroll-into-view 後に element が hidden 化
                # する競合を避けるため、 click ではなく dispatch_event("click") で
                # MouseEvent を直接 dispatch する (bbox/scroll 不要、 force=True と
                # 異なり座標が無くても発火可能)。 :visible filter は前年要素の
                # 誤発火を防ぐため引き続き使用、 click 直前に locator を再解決する。
                await p.wait_for_function(
                    "(sel) => Array.from(document.querySelectorAll(sel))"
                    ".some(el => el.offsetParent !== null)",
                    arg=f'li[data-year="{year}"][data-month="{month}"]',
                    timeout=10_000,
                )
                month_li = p.locator(
                    f'li[data-year="{year}"][data-month="{month}"]:visible'
                ).first
                await month_li.dispatch_event("click")
                await p.wait_for_load_state("networkidle")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    "Month switcher failed (%d/%d): %s", year, month, exc
                )
                self._inc_stat(f"{self.name}/months_failed")
                return

            html = await p.content()

        monthly = response.replace(body=html.encode("utf-8"))
        count = 0
        for item in parse_transactions(monthly):
            count += 1
            yield item
        self._inc_stat(f"{self.name}/records", count=count)
        self._inc_stat(f"{self.name}/months_fetched")
        self.logger.info("Fetched %d txns for %04d/%02d", count, year, month)
