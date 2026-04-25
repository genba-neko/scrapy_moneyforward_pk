"""Helpers for composing Playwright-enabled Scrapy requests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from scrapy_playwright.page import PageMethod


async def init_page_block_static(page, request) -> None:  # noqa: ARG001
    """Block images / fonts / media to speed up navigation."""

    async def _route(route):
        if route.request.resource_type in {"image", "font", "media", "stylesheet"}:
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


@asynccontextmanager
async def managed_page(page):
    """Ensure a Playwright page is unrouted + closed when a callback exits."""
    try:
        yield page
    finally:
        try:
            await page.unroute("**/*")
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            await page.close()
        except Exception:  # noqa: BLE001, S110
            pass
