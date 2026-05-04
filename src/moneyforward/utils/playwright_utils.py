"""Helpers for composing Playwright-enabled Scrapy requests."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Any

from scrapy_playwright.page import PageMethod

# Resource types we always discard. ``stylesheet`` is intentionally absent:
# MoneyForward injects layout-critical CSS at runtime and blocking it
# breaks the DOM the parsers expect.
_BLOCK_RESOURCE_TYPES = frozenset({"image", "font", "media"})

# URL allow-list: requests whose URL matches any of these patterns are
# blocked even when the resource_type is otherwise harmless. Used to drop
# analytics / advertising endpoints that bloat captures and emit data
# outside our trust boundary.
_BLOCK_URL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"google-analytics\.com", re.IGNORECASE),
    re.compile(r"googletagmanager\.com", re.IGNORECASE),
    re.compile(r"hotjar\.com", re.IGNORECASE),
    re.compile(r"doubleclick\.net", re.IGNORECASE),
    re.compile(r"facebook\.(com|net)/tr", re.IGNORECASE),
)


def _should_block(resource_type: str, url: str) -> bool:
    """Return True when the request should be aborted by ``init_page_block_static``."""
    if resource_type in _BLOCK_RESOURCE_TYPES:
        return True
    return any(p.search(url) for p in _BLOCK_URL_PATTERNS)


async def init_page_block_static(page, request) -> None:  # noqa: ARG001
    """Block heavy assets and analytics endpoints to speed up navigation."""

    async def _route(route):
        if _should_block(route.request.resource_type, route.request.url):
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", _route)


def build_playwright_meta(
    *,
    include_page: bool = False,
    page_methods: list[PageMethod] | None = None,
    context: str = "default",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose ``Request.meta`` for a Playwright-driven request."""
    methods = page_methods or [PageMethod("wait_for_load_state", "domcontentloaded")]
    meta: dict[str, Any] = {
        "playwright": True,
        "playwright_context": context,
        "playwright_include_page": include_page,
        "playwright_page_init_callback": init_page_block_static,
        "playwright_page_methods": methods,
    }
    if extra:
        meta.update(extra)
    return meta


async def close_page_quietly(page) -> None:
    """Unroute and close a Playwright page, swallowing teardown exceptions.

    Shared by ``managed_page`` (callback path) and the errback close path so
    both code paths converge on the same teardown order.
    """
    try:
        await page.unroute("**/*")
    except Exception:  # noqa: BLE001, S110
        pass
    try:
        await page.close()
    except Exception:  # noqa: BLE001, S110
        pass


@asynccontextmanager
async def managed_page(page):
    """Ensure a Playwright page is unrouted + closed when a callback exits."""
    try:
        yield page
    finally:
        await close_page_quietly(page)
