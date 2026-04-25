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
from typing import Any, AsyncIterator, Iterable, cast

import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod

from moneyforward_pk.utils.logging_config import setup_common_logging
from moneyforward_pk.utils.playwright_utils import (
    build_playwright_meta,
    close_page_quietly,
    managed_page,
)
from moneyforward_pk.utils.session_utils import is_session_expired

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
        # Optional alternative credential pair for fallback when the primary
        # account is locked / temporarily refused. Loaded from settings in
        # ``from_crawler`` and never logged. Empty strings disable the path.
        self.login_alt_user: str = ""
        self.login_alt_pass: str = ""

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        # Configure logging once per crawler boot. Doing this at module import
        # time would mutate root logger state simply by importing the spider,
        # which makes unit tests and reusable library imports unsafe.
        setup_common_logging()
        spider = super().from_crawler(crawler, *args, **kwargs)
        settings = crawler.settings
        if not spider.login_user:
            spider.login_user = settings.get("SITE_LOGIN_USER", "")
        if not spider.login_pass:
            spider.login_pass = settings.get("SITE_LOGIN_PASS", "")
        # Alt credentials are env-only (do not allow CLI override to avoid
        # leaking secrets via shell history).
        spider.login_alt_user = settings.get("SITE_LOGIN_ALT_USER", "") or ""
        spider.login_alt_pass = settings.get("SITE_LOGIN_ALT_PASS", "") or ""
        if not spider.login_user or not spider.login_pass:
            spider.logger.warning(
                "SITE_LOGIN_USER / SITE_LOGIN_PASS not configured; login will fail."
            )
        return spider

    # ----------------------------------------------------------- credentials

    def _resolve_credentials(self, attempt: int) -> tuple[str, str]:
        """Pick the credential pair for a given login attempt.

        Parameters
        ----------
        attempt : int
            Zero-based login attempt counter. ``0`` selects the primary
            credentials. ``>= 1`` falls back to ``SITE_LOGIN_ALT_USER`` /
            ``SITE_LOGIN_ALT_PASS`` when both are configured.

        Returns
        -------
        tuple[str, str]
            ``(user, password)`` to use for this attempt. Returns the primary
            pair when alt credentials are unset so behavior is unchanged for
            users who do not configure the alt path.
        """
        if attempt >= 1 and self.login_alt_user and self.login_alt_pass:
            return self.login_alt_user, self.login_alt_pass
        return (self.login_user or "", self.login_pass or "")

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

    def _build_login_request(
        self,
        *,
        follow_up: scrapy.Request | None = None,
        login_attempt: int = 0,
    ) -> scrapy.Request:
        meta = build_playwright_meta(
            include_page=True,
            page_methods=[
                PageMethod("wait_for_load_state", "domcontentloaded"),
            ],
        )
        if follow_up is not None:
            meta["moneyforward_follow_up"] = follow_up
        meta["moneyforward_login_attempt"] = login_attempt
        return scrapy.Request(
            url=self.start_url,
            callback=self._parse_after_login,
            errback=self.errback_playwright,
            dont_filter=True,
            meta=meta,
        )

    def handle_force_login(self, retry_request: scrapy.Request) -> scrapy.Request:
        """Wrap a session-expiry retry with a fresh login flow.

        Parameters
        ----------
        retry_request : scrapy.Request
            The request the middleware would otherwise re-download. Carries
            ``meta["moneyforward_force_login"]`` set by the middleware.

        Returns
        -------
        scrapy.Request
            A new login request that, after ``login_flow`` succeeds, queues
            ``retry_request`` via ``after_login``. The login attempt counter
            in ``retry_request.meta["login_retry_times"]`` is propagated to
            ``moneyforward_login_attempt`` so the alt-credential fallback in
            ``_resolve_credentials`` can engage on retries.
        """
        # Strip the consumed flag so the follow-up does not loop back here.
        retry_request.meta.pop("moneyforward_force_login", None)
        # PlaywrightSessionMiddleware bumps login_retry_times before handing
        # control here. Mirror that counter into the login request so
        # ``login_flow`` can pick alt credentials when configured.
        attempt = int(retry_request.meta.get("login_retry_times", 0))
        self._inc_stat(f"{self.name}/login/forced")
        if attempt >= 1 and self.login_alt_user and self.login_alt_pass:
            self._inc_stat(f"{self.name}/login/alt_user_used")
        return self._build_login_request(follow_up=retry_request, login_attempt=attempt)

    # ---------------------------------------------------------------- login

    async def login_flow(self, page, *, login_attempt: int = 0) -> None:
        """Drive the moneyforward.com login UI via Playwright.

        Parameters
        ----------
        page : playwright.async_api.Page
            Page handle delivered by scrapy-playwright.
        login_attempt : int, optional
            Zero-based login attempt counter. Forwarded to
            ``_resolve_credentials`` so alt credentials can engage on
            retries when configured.
        """
        timeout = self.login_timeout_ms
        user, password = self._resolve_credentials(login_attempt)

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
        await page.fill('input[name="mfid_user[email]"]', user)
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)

        # Step 2: password (presented on a separate page)
        await page.fill(
            'input[name="mfid_user[password]"], input[type="password"]',
            password,
        )
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=timeout)

    async def _parse_after_login(self, response: Response):
        page = response.meta.get("playwright_page")
        if page is None:
            self.logger.error("No playwright_page attached to login response")
            return

        login_attempt = int(response.meta.get("moneyforward_login_attempt", 0))

        async with managed_page(page) as p:
            try:
                await self.login_flow(p, login_attempt=login_attempt)
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

        follow_up = response.meta.get("moneyforward_follow_up")
        if follow_up is not None:
            self.logger.info("Replaying request after forced login: %s", follow_up.url)
            yield follow_up
            return

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
        """Close the Playwright page on download failure.

        Pops ``playwright_page`` from meta so ``managed_page`` (callback path)
        cannot double-close. Routes the actual teardown through
        ``close_page_quietly`` so callback and errback paths share the
        unroute → close sequence (single close strategy).
        """
        self.logger.error("Playwright request failed: %s", failure)
        self._inc_stat(f"{self.name}/playwright/errback")
        page = failure.request.meta.pop("playwright_page", None)
        if page is None:
            return
        try:
            import asyncio

            close_coro = close_page_quietly(page)
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():
                asyncio.ensure_future(close_coro)
            else:
                # No running loop (sync test path): drop the unawaited coro
                # explicitly so we do not leak a "coroutine never awaited" warning.
                if hasattr(close_coro, "close"):
                    close_coro.close()
        except Exception:  # noqa: BLE001, S110
            pass


class XMoneyforwardLoginMixin:
    """Alternative login flow for ``*.x.moneyforward.com`` partner portals."""

    async def login_flow(self, page, *, login_attempt: int = 0) -> None:  # type: ignore[override]
        timeout = getattr(self, "login_timeout_ms", 60_000)
        resolver = getattr(self, "_resolve_credentials", None)
        if callable(resolver):
            resolved = cast("tuple[str, str]", resolver(login_attempt))
            login_user, login_pass = resolved
        else:
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
