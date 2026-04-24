"""Base Spider: Playwright login + session handling for MoneyForward.

Subclasses override:
- ``start_url`` (top page, optional — defaults to ``https://moneyforward.com/``)
- ``login_flow(page)`` — async coroutine that drives the login UI
- ``after_login(response)`` — yields the first authenticated requests
- ``is_partner_portal`` — set True for x.moneyforward.com variants

Login flow defaults target the ``moneyforward.com`` (mfid_user) form. The
``x.moneyforward.com`` partner-portal flow (``sign_in_session_service``) is
implemented in ``XMoneyforwardLoginMixin``.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Iterable

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from moneyforward_pk.utils.logging_config import setup_common_logging
from moneyforward_pk.utils.playwright_utils import (
    build_playwright_meta,
    managed_page,
)
from moneyforward_pk.utils.session_utils import is_session_expired

setup_common_logging()

logger = logging.getLogger(__name__)


class MoneyforwardBase(scrapy.Spider):
    """Common foundation. Handles login + errback."""

    start_url: str = "https://moneyforward.com/"
    is_partner_portal: bool = False
    login_timeout_ms: int = 60_000

    def __init__(
        self,
        *args: Any,
        login_user: str | None = None,
        login_pass: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.login_user = login_user
        self.login_pass = login_pass

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        settings = crawler.settings
        if not spider.login_user:
            spider.login_user = settings.get("SITE_LOGIN_USER", "")
        if not spider.login_pass:
            spider.login_pass = settings.get("SITE_LOGIN_PASS", "")
        if not spider.login_user or not spider.login_pass:
            spider.logger.warning(
                "SITE_LOGIN_USER / SITE_LOGIN_PASS not configured; login will fail."
            )
        return spider

    # --------------------------------------------------------------- helpers

    def _inc_stat(self, key: str, count: int = 1) -> None:
        """Increment a stats counter if a crawler is attached."""
        crawler = getattr(self, "crawler", None)
        if crawler is None or crawler.stats is None:
            return
        crawler.stats.inc_value(key, count=count)

    # ------------------------------------------------------------------ start

    async def start(self) -> AsyncIterator[scrapy.Request]:
        """Scrapy 2.13+ async start entry point."""
        yield self._build_login_request()

    def start_requests(self) -> Iterable[scrapy.Request]:
        """Back-compat for Scrapy versions that still call start_requests."""
        yield self._build_login_request()

    def _build_login_request(self) -> scrapy.Request:
        return scrapy.Request(
            url=self.start_url,
            callback=self._parse_after_login,
            errback=self.errback_playwright,
            dont_filter=True,
            meta=build_playwright_meta(
                include_page=True,
                page_methods=[
                    PageMethod("wait_for_load_state", "domcontentloaded"),
                ],
            ),
        )

    # ---------------------------------------------------------------- login

    async def login_flow(self, page) -> None:
        """Drive the moneyforward.com login UI via Playwright."""
        timeout = self.login_timeout_ms

        await page.wait_for_load_state("domcontentloaded", timeout=timeout)

        # Top page → /sign_in
        sign_in_link = page.locator('a[href="/sign_in"]').first
        if await sign_in_link.count() > 0:
            await sign_in_link.click(timeout=timeout)
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)

        # /sign_in → /sign_in/email
        email_link = page.locator('a[href^="/sign_in/email"]').first
        if await email_link.count() > 0:
            await email_link.click(timeout=timeout)
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)

        # Step 1: email
        await page.fill('input[name="mfid_user[email]"]', self.login_user or "")
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)

        # Step 2: password (presented on a separate page)
        await page.fill(
            'input[name="mfid_user[password]"], input[type="password"]',
            self.login_pass or "",
        )
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=timeout)

    async def _parse_after_login(self, response: Response):
        page = response.meta.get("playwright_page")
        if page is None:
            self.logger.error("No playwright_page attached to login response")
            return

        async with managed_page(page) as p:
            try:
                await self.login_flow(p)
            except Exception as exc:  # noqa: BLE001
                self.logger.exception("Login flow failed: %s", exc)
                self._inc_stat(f"{self.name}/login/failed")
                return

            current_url = p.url
            title = await p.title()
            self.logger.info("Login complete: url=%s title=%s", current_url, title)

            # Bridge page → HtmlResponse for downstream parsing.
            html = await p.content()

        post_login = response.replace(url=current_url, body=html.encode("utf-8"))

        if is_session_expired(post_login):
            self.logger.error("Still on login page after login_flow")
            self._inc_stat(f"{self.name}/login/still_on_login")
            return

        self._inc_stat(f"{self.name}/login/success")
        async for item_or_request in self._iter_after_login(post_login):
            yield item_or_request

    async def _iter_after_login(self, response: Response):
        result = self.after_login(response)
        if result is None:
            return
        if hasattr(result, "__aiter__"):
            async for x in result:  # type: ignore[attr-defined]
                yield x
        else:
            for x in result:  # type: ignore[union-attr]
                yield x

    # ---------------------------------------------------------------- hooks

    def after_login(self, response: Response):  # noqa: ARG002
        """Override in subclass to yield authenticated requests."""
        return iter(())

    # ---------------------------------------------------------------- errbacks

    def errback_playwright(self, failure) -> None:
        self.logger.error("Playwright request failed: %s", failure)
        self._inc_stat(f"{self.name}/playwright/errback")
        page = failure.request.meta.get("playwright_page")
        if page is not None:
            try:
                import asyncio

                asyncio.ensure_future(page.close())
            except Exception:  # noqa: BLE001, S110
                pass


class XMoneyforwardLoginMixin:
    """Alternative login flow for ``*.x.moneyforward.com`` partner portals."""

    async def login_flow(self, page) -> None:  # type: ignore[override]
        timeout = getattr(self, "login_timeout_ms", 60_000)
        login_user = getattr(self, "login_user", "") or ""
        login_pass = getattr(self, "login_pass", "") or ""

        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
        entry = page.locator('a[href="/users/sign_in"]').first
        if await entry.count() > 0:
            await entry.click(timeout=timeout)
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)

        await page.fill('input[name="sign_in_session_service[email]"]', login_user)
        await page.fill('input[name="sign_in_session_service[password]"]', login_pass)
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=timeout)
