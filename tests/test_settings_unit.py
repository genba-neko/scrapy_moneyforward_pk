"""Settings module imports and exposes Playwright wiring."""

from __future__ import annotations


def test_settings_import_and_keys():
    from moneyforward import settings

    assert settings.BOT_NAME == "moneyforward"
    assert settings.SPIDER_MODULES == ["moneyforward.spiders"]
    assert settings.TWISTED_REACTOR == (
        "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
    )
    assert (
        settings.DOWNLOAD_HANDLERS["https"]
        == "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler"
    )
    assert settings.PLAYWRIGHT_BROWSER_TYPE == "chromium"
    assert isinstance(settings.PLAYWRIGHT_CONTEXTS, dict)
    assert settings.SITE_PAST_MONTHS >= 1


def test_playwright_contexts_intentionally_empty():
    """Pre-populating 'default' breaks storage_state injection; must stay empty."""
    from moneyforward import settings

    assert "default" not in settings.PLAYWRIGHT_CONTEXTS


def test_retry_http_codes_excludes_400():
    """400 is a non-retryable client error; legacy list must drop it.

    iter2 T2: re-driving a 400 cannot fix the request shape, so re-trying
    just wastes credentials and login attempts.
    """
    from moneyforward import settings

    assert 400 not in settings.RETRY_HTTP_CODES
    # Common transient codes must remain.
    assert 503 in settings.RETRY_HTTP_CODES
    assert 429 in settings.RETRY_HTTP_CODES
