"""Minimal test doubles for Scrapy + Playwright."""

from __future__ import annotations

from typing import Any

from scrapy.http import HtmlResponse, Request


class FakeStats:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def inc_value(self, key: str, count: int = 1, **_: Any) -> None:
        self.values[key] = self.values.get(key, 0) + count

    def get_value(self, key: str, default: int = 0) -> int:
        return self.values.get(key, default)


class FakeCrawler:
    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.stats = FakeStats()
        self._settings = settings or {}

    @property
    def settings(self):
        from scrapy.settings import Settings

        return Settings(self._settings)


def make_response(
    body: str, url: str = "https://moneyforward.com/", encoding: str = "utf-8"
) -> HtmlResponse:
    return HtmlResponse(
        url=url,
        body=body.encode(encoding),
        encoding=encoding,
        request=Request(url=url),
    )
