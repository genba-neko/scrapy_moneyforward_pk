"""Asset allocation spider (/bs/portfolio)."""

from __future__ import annotations

from typing import AsyncIterator

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from moneyforward_pk.spiders._parsers import parse_asset_allocation
from moneyforward_pk.spiders.base.moneyforward_base import MoneyforwardBase
from moneyforward_pk.utils.playwright_utils import (
    build_playwright_meta,
    managed_page,
)

PORTFOLIO_URL = "https://moneyforward.com/bs/portfolio"


class MfAssetAllocationSpider(MoneyforwardBase):
    name = "mf_asset_allocation"
    allowed_domains = ["moneyforward.com"]

    async def after_login(self, response: Response) -> AsyncIterator[scrapy.Request]:  # type: ignore[override]
        yield scrapy.Request(
            url=PORTFOLIO_URL,
            callback=self.parse_portfolio,
            errback=self.errback_playwright,
            dont_filter=True,
            meta=build_playwright_meta(
                include_page=True,
                page_methods=[
                    PageMethod("wait_for_load_state", "networkidle"),
                ],
            ),
        )

    async def parse_portfolio(self, response: Response):
        page = response.meta.get("playwright_page")
        if page is None:
            return
        async with managed_page(page) as p:
            html = await p.content()

        portfolio = response.replace(body=html.encode("utf-8"))
        count = 0
        for item in parse_asset_allocation(portfolio, self.name, self.login_user or ""):
            count += 1
            yield item
        self._inc_stat(f"{self.name}/records", count=count)
        self.logger.info("Fetched %d asset-allocation rows", count)
