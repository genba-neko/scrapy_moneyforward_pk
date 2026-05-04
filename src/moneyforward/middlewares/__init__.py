"""Downloader middlewares for moneyforward."""

from moneyforward.middlewares.html_inspector import HtmlInspectorMiddleware
from moneyforward.middlewares.playwright_session import (
    PlaywrightSessionMiddleware,
)

__all__ = ["HtmlInspectorMiddleware", "PlaywrightSessionMiddleware"]
