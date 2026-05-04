"""Asset allocation spider (/bs/portfolio)."""

from __future__ import annotations

from typing import AsyncIterator
from urllib.parse import urlparse

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from moneyforward.spiders._parsers import parse_asset_allocation
from moneyforward.spiders.base.moneyforward_base import MoneyforwardBase
from moneyforward.utils.playwright_utils import (
    build_playwright_meta,
    managed_page,
)


class MfAssetAllocationSpider(MoneyforwardBase):
    """Visit /bs/portfolio and parse asset-allocation rows."""

    name = "asset_allocation"
    spider_type = "asset_allocation"
    variant_name = "mf"  # default; overridden via ``site`` kwarg

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # variant の base_url から allowed_domains を動的決定 (派生サイト対応).
        self.allowed_domains = [urlparse(self.variant.base_url).netloc]

    async def after_login(self, response: Response) -> AsyncIterator[scrapy.Request]:  # type: ignore[override]
        yield scrapy.Request(
            url=self.variant.asset_allocation_url,
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
        # Compose the legacy spider_name used in asset_item_key
        # (``{site}_{spider_type}``) from registry + class attribute, so the
        # output key remains identical to the original PJ format even after
        # consolidating to a single AssetAllocation spider class.
        spider_key_prefix = f"{self.variant.name}_{self.spider_type}"
        for item in parse_asset_allocation(
            portfolio, spider_key_prefix, self.login_user or ""
        ):
            count += 1
            yield item
        self._inc_stat(f"{self.name}/records", count=count)
        self.logger.info("Fetched %d asset-allocation rows", count)
