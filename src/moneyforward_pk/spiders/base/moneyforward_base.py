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

from moneyforward_pk.auth import SessionManager
from moneyforward_pk.spiders.variants import VariantConfig, get_variant
from moneyforward_pk.utils.logging_config import setup_common_logging
from moneyforward_pk.utils.paths import PROJECT_ROOT
from moneyforward_pk.utils.playwright_utils import (
    build_playwright_meta,
    close_page_quietly,
    managed_page,
)
from moneyforward_pk.utils.session_utils import is_session_expired

logger = logging.getLogger(__name__)


class MoneyforwardBase(scrapy.Spider):
    """Common foundation. Handles login + errback.

    Subclasses declare ``variant_name`` (registry key in ``VARIANTS``) and the
    base resolves ``self.variant`` so URL / login-form selectors come from the
    declarative registry rather than hardcoded module constants.
    """

    # variant_name のデフォルトは "mf" (既存 mf_* スパイダー互換).
    variant_name: str = "mf"
    # start_url / is_partner_portal は variant から動的に上書きされる.
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
        # variant 解決: クラス属性 ``variant_name`` をキーに registry を引く.
        self.variant: VariantConfig = get_variant(self.variant_name)
        # variant の値で start_url / is_partner_portal を上書き.
        self.start_url = self.variant.base_url
        self.is_partner_portal = self.variant.is_partner_portal
        self.login_user = login_user
        self.login_pass = login_pass
        # Optional alternative credential pair for fallback when the primary
        # account is locked / temporarily refused. Loaded from settings in
        # ``from_crawler`` and never logged. Empty strings disable the path.
        self.login_alt_user: str = ""
        self.login_alt_pass: str = ""
        # SessionManager is wired in ``from_crawler`` once the crawler is
        # attached so ``runtime/state`` is resolved relative to PROJECT_ROOT.
        self.session_manager: SessionManager | None = None

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
        # Issue #43: session persistence — one storage_state file per
        # (variant, login_user). When the file exists at request time the
        # request is sent with ``playwright_context_kwargs={"storage_state":
        # ...}`` so Playwright reuses the cookies and login_flow becomes
        # a no-op. The state is refreshed after every successful login.
        if spider.login_user:
            # PROJECT_ROOT is src/.. (computed in utils/paths.py with the
            # correct parents[3] count from the utils module). Use it to
            # avoid the parents[N] off-by-one bug that placed state files
            # under src/runtime/ during the initial implementation.
            state_dir = PROJECT_ROOT / "runtime" / "state"
            spider.session_manager = SessionManager(
                state_dir=state_dir,
                site=spider.variant_name,
                login_user=spider.login_user,
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
        # Issue #43: inject a saved storage_state when one is on disk so
        # Playwright reuses the existing logged-in session. login_flow then
        # detects "already logged in" and skips form filling.
        if self.session_manager is not None:
            state_path = self.session_manager.get_storage_state()
            if state_path:
                meta["playwright_context_kwargs"] = {"storage_state": state_path}
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

    async def _is_logged_in_page(self, page) -> bool:
        """Return True if the current page indicates an authenticated session.

        Heuristic: presence of a logout link (``a[href*="/sign_out"]``) and
        the URL not pointing at a sign-in / signup form. MoneyForward and
        all partner portals render a logout link in the top-right header
        whenever the user is logged in.
        """
        try:
            url = page.url or ""
            # Already on a login form → definitely not logged in.
            if "/sign_in" in url or "/users/sign_up" in url:
                return False
            logout = page.locator('a[href*="/sign_out"]').first
            return await logout.count() > 0
        except Exception:  # noqa: BLE001
            return False

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

        Notes
        -----
        Issue #43: navigates **directly** to ``variant.login_url`` instead
        of clicking the top-page header link. The header DOM differs
        across mf/xmf variants and is JS-rendered in some cases, which
        made the previous ``a[href=...]`` click-based flow brittle. Going
        straight to the form bypasses that entirely.
        """
        timeout = self.login_timeout_ms
        user, password = self._resolve_credentials(login_attempt)
        email_field = self.variant.login_form_email
        password_field = self.variant.login_form_password
        login_url = self.variant.login_url

        self.logger.info(
            "login_flow start: variant=%s login_url=%s current_url=%s",
            self.variant.name,
            login_url,
            page.url,
        )

        # Always navigate to the explicit login URL. ``wait_for_selector``
        # is more reliable than ``wait_for_load_state`` for SPA-ish pages
        # because it actually waits until the form is present.
        await page.goto(login_url, wait_until="domcontentloaded", timeout=timeout)
        self.logger.info("login_flow: after goto current_url=%s", page.url)

        await page.wait_for_selector(f'input[name="{email_field}"]', timeout=timeout)
        self.logger.info("login_flow: email input visible")

        # Probe password field on same page → 1-page form vs 2-page form.
        password_locator = page.locator(f'input[name="{password_field}"]')
        password_count = await password_locator.count()
        single_page = password_count > 0
        self.logger.info(
            "login_flow: form layout = %s (password_count=%d)",
            "1-page" if single_page else "2-page",
            password_count,
        )

        await page.fill(f'input[name="{email_field}"]', user)
        if single_page:
            await page.fill(f'input[name="{password_field}"]', password)
            await page.click('button[type="submit"], input[type="submit"]')
        else:
            # Step 1: submit email
            await page.click('button[type="submit"], input[type="submit"]')
            await page.wait_for_selector(
                f'input[name="{password_field}"], input[type="password"]',
                timeout=timeout,
            )
            # Step 2: submit password
            await page.fill(
                f'input[name="{password_field}"], input[type="password"]',
                password,
            )
            await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=timeout)
        self.logger.info("login_flow: complete current_url=%s", page.url)

    async def _parse_after_login(self, response: Response):
        """Login callback. Returns a **list** of follow-up items/requests.

        Note: returns a list (not an async generator) to avoid Scrapy's
        lazy async-iteration that pulls one yield at a time. With async
        generators, after the first yield the engine schedules that
        request, processes it, finds the scheduler empty (because the
        generator is paused mid-loop), and closes the spider — losing
        the remaining N-1 requests. Returning a list eagerly enqueues
        all of them. Issue #43 root cause for "1/12 months fetched".
        """
        page = response.meta.get("playwright_page")
        if page is None:
            self.logger.error("No playwright_page attached to login response")
            return []

        login_attempt = int(response.meta.get("moneyforward_login_attempt", 0))

        async with managed_page(page) as p:
            # Issue #43: when a stored storage_state was injected and the
            # session is still valid, the page is already authenticated.
            # Skip login_flow in that case to avoid the bot-detection risk
            # of repeatedly re-logging in.
            already_logged_in = await self._is_logged_in_page(p)
            if already_logged_in:
                self.logger.info("Reusing saved session (login_flow skipped)")
                self._inc_stat(f"{self.name}/login/skipped")
            else:
                try:
                    await self.login_flow(p, login_attempt=login_attempt)
                except Exception as exc:  # noqa: BLE001
                    self.logger.exception("Login flow failed: %s", exc)
                    self._inc_stat(f"{self.name}/login/failed")
                    if self.session_manager is not None:
                        # Drop the (now-known-bad) state file so the next
                        # invocation starts from a clean login.
                        self.session_manager.invalidate_session()
                    return []

            current_url = p.url
            title = await p.title()
            self.logger.info("Login complete: url=%s title=%s", current_url, title)

            # Persist the post-login storage_state so the next spider
            # invocation can reuse the cookies. Failure is non-fatal.
            if self.session_manager is not None:
                await self.session_manager.save_from_context(p.context)

            # Bridge page → HtmlResponse for downstream parsing.
            html = await p.content()

        post_login = response.replace(url=current_url, body=html.encode("utf-8"))

        if is_session_expired(post_login):
            self.logger.error("Still on login page after login_flow")
            self._inc_stat(f"{self.name}/login/still_on_login")
            return []

        self._inc_stat(f"{self.name}/login/success")

        follow_up = response.meta.get("moneyforward_follow_up")
        if follow_up is not None:
            self.logger.info("Replaying request after forced login: %s", follow_up.url)
            return [follow_up]

        results: list = []
        async for item_or_request in self._iter_after_login(post_login):
            results.append(item_or_request)
        self.logger.info(
            "_parse_after_login: returning %d follow-up items/requests",
            len(results),
        )
        return results

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
    """Backward-compat alias.

    Issue #43: ``MoneyforwardBase.login_flow`` now drives both mf and
    partner-portal logins by branching on ``variant.is_partner_portal``
    and navigating directly to ``variant.login_url``. This mixin no
    longer needs to override ``login_flow``; it remains as a marker
    class so existing ``isinstance(spider, XMoneyforwardLoginMixin)``
    checks keep working.
    """
