"""Resource-blocking policy and managed_page semantics."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from moneyforward_pk.utils.playwright_utils import (
    _BLOCK_RESOURCE_TYPES,
    _should_block,
    close_page_quietly,
    init_page_block_static,
    managed_page,
)


def test_block_set_excludes_stylesheet():
    """Stylesheet must NOT be in the default block set (layout-critical CSS)."""
    assert "stylesheet" not in _BLOCK_RESOURCE_TYPES


def test_block_set_includes_image_font_media():
    assert {"image", "font", "media"}.issubset(_BLOCK_RESOURCE_TYPES)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google-analytics.com/collect",
        "https://googletagmanager.com/gtm.js",
        "https://static.hotjar.com/c/hotjar.js",
        "https://stats.g.doubleclick.net/r/collect",
        "https://www.facebook.com/tr",
    ],
)
def test_should_block_url_pattern_matches_analytics(url: str):
    assert _should_block("script", url) is True


def test_should_block_lets_stylesheet_pass():
    assert _should_block("stylesheet", "https://moneyforward.com/app.css") is False


def test_should_block_lets_first_party_script_pass():
    assert _should_block("script", "https://moneyforward.com/app.js") is False


def test_should_block_blocks_image_resource_type():
    assert _should_block("image", "https://moneyforward.com/logo.png") is True


def test_init_page_block_static_route_handler_logic():
    """Inspect the routing decision without an event loop."""
    page = MagicMock()
    page.route = AsyncMock()

    import asyncio

    async def drive():
        await init_page_block_static(page, MagicMock())

    asyncio.new_event_loop().run_until_complete(drive())
    assert page.route.await_count == 1
    # The first arg of route(...) must be the catch-all glob.
    args, _ = page.route.call_args
    assert args[0] == "**/*"


def test_close_page_quietly_swallows_unroute_failure():
    """Failure during unroute must not bubble out."""
    import asyncio

    page = MagicMock()

    class _Boom:
        def __await__(self):
            raise RuntimeError("unroute boom")
            yield  # pragma: no cover

    page.unroute = MagicMock(return_value=_Boom())
    page.close = AsyncMock()

    asyncio.new_event_loop().run_until_complete(close_page_quietly(page))
    page.close.assert_awaited_once()


def test_close_page_quietly_swallows_close_failure():
    import asyncio

    page = MagicMock()
    page.unroute = AsyncMock()

    class _Boom:
        def __await__(self):
            raise RuntimeError("close boom")
            yield  # pragma: no cover

    page.close = MagicMock(return_value=_Boom())

    # Must not raise.
    asyncio.new_event_loop().run_until_complete(close_page_quietly(page))


def test_managed_page_exits_via_close_page_quietly():
    """managed_page yields the page and closes via the shared helper on exit."""
    import asyncio

    page = MagicMock()
    page.unroute = AsyncMock()
    page.close = AsyncMock()

    async def drive() -> Any:
        async with managed_page(page) as p:
            return p

    result = asyncio.new_event_loop().run_until_complete(drive())
    assert result is page
    page.unroute.assert_awaited_once_with("**/*")
    page.close.assert_awaited_once()
