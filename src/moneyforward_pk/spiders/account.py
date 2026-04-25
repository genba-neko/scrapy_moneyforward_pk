"""Account spider (/accounts, with update-button click + polling)."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator
from urllib.parse import urlparse

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from moneyforward_pk.spiders._parsers import parse_accounts
from moneyforward_pk.spiders.base.moneyforward_base import MoneyforwardBase
from moneyforward_pk.utils.playwright_utils import (
    build_playwright_meta,
    managed_page,
)


class MfAccountSpider(MoneyforwardBase):
    """Visit /accounts, trigger updates, poll until no 更新中 remain."""

    name = "mf_account"
    variant_name = "mf"
    update_wait_seconds = 20
    update_max_retry = 5

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # variant の base_url から allowed_domains を動的決定 (派生サイト対応).
        self.allowed_domains = [urlparse(self.variant.base_url).netloc]

    async def after_login(self, response: Response) -> AsyncIterator[scrapy.Request]:  # type: ignore[override]
        yield self._accounts_request(is_update=True, attempt=0)

    def _accounts_request(self, *, is_update: bool, attempt: int) -> scrapy.Request:
        return scrapy.Request(
            url=self.variant.accounts_url,
            callback=self.parse_accounts_page,
            errback=self.errback_playwright,
            cb_kwargs={"is_update": is_update, "attempt": attempt},
            dont_filter=True,
            meta=build_playwright_meta(
                include_page=True,
                page_methods=[
                    PageMethod("wait_for_load_state", "domcontentloaded"),
                ],
            ),
        )

    async def parse_accounts_page(
        self, response: Response, is_update: bool, attempt: int
    ):
        page = response.meta.get("playwright_page")
        if page is None:
            return

        async with managed_page(page) as p:
            if is_update:
                await self._click_update_buttons(p)
            html = await p.content()

        parsed = response.replace(body=html.encode("utf-8"))
        items, is_updating = parse_accounts(parsed)

        if is_updating and attempt < self.update_max_retry:
            self.logger.info(
                "Accounts still updating; retry %d/%d in %ds",
                attempt + 1,
                self.update_max_retry,
                self.update_wait_seconds,
            )
            await asyncio.sleep(self.update_wait_seconds)
            yield self._accounts_request(is_update=False, attempt=attempt + 1)
            return

        for item in items:
            yield item
        self._inc_stat(f"{self.name}/records", count=len(items))
        self.logger.info("Fetched %d account rows", len(items))

    async def _click_update_buttons(self, page) -> None:
        """Click every 更新 button in the account table."""
        try:
            buttons = page.locator('td form input[value="更新"]')
            total = await buttons.count()
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Failed to enumerate update buttons: %s", exc)
            return

        self.logger.info("Clicking %d update buttons", total)
        for idx in range(total):
            try:
                await buttons.nth(idx).click(timeout=5_000)
                await page.wait_for_timeout(1_000)
            except Exception as exc:  # noqa: BLE001
                # Promote silent debug to a stats counter so operators can see
                # transient update-button failures without DEBUG-level logs.
                self.logger.debug("Update button %d click failed: %s", idx, exc)
                self._inc_stat(f"{self.name}/update_button_click_failed")
