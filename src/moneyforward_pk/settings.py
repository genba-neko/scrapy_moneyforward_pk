"""Scrapy settings for moneyforward_pk project."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_ROOT / "runtime"

# .env load (skip during pytest to preserve test-controlled env)
if "pytest" not in sys.modules:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def _resolve_project_path(value: str | os.PathLike[str], default: Path) -> Path:
    """Resolve a possibly-relative path against PROJECT_ROOT."""
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


BOT_NAME = "moneyforward_pk"

SPIDER_MODULES = ["moneyforward_pk.spiders"]
NEWSPIDER_MODULE = "moneyforward_pk.spiders"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS = 1
DOWNLOAD_DELAY = 3.0
RANDOMIZE_DOWNLOAD_DELAY = True

RETRY_ENABLED = True
RETRY_TIMES = 4
RETRY_HTTP_CODES = [500, 502, 503, 504, 520, 522, 524, 408, 429]

# Playwright wiring
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": os.environ.get("MONEYFORWARD_HEADLESS", "true").lower() != "false",
    "args": ["--disable-blink-features=AutomationControlled"],
}
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 120_000
# Intentionally empty: first request supplies storage_state via
# playwright_context_kwargs. Pre-populating "default" here creates the context
# before the first request can inject a stored session.
PLAYWRIGHT_CONTEXTS: dict[str, dict] = {}

DOWNLOADER_MIDDLEWARES = {
    "moneyforward_pk.middlewares.playwright_session.PlaywrightSessionMiddleware": 600,
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": 810,
}

ITEM_PIPELINES = {
    "moneyforward_pk.pipelines.JsonOutputPipeline": 300,
}

FEED_EXPORT_ENCODING = "utf-8"

# MoneyForward credentials / tunables
SITE_LOGIN_USER = os.environ.get("SITE_LOGIN_USER", "")
SITE_LOGIN_PASS = os.environ.get("SITE_LOGIN_PASS", "")
SITE_LOGIN_ALT_USER = os.environ.get("SITE_LOGIN_ALT_USER", "")
SITE_PAST_MONTHS = int(os.environ.get("SITE_PAST_MONTHS", "12"))

# JSON output (replaces the legacy DynamoDB pipeline; USER_DIRECTIVES)
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "")
OUTPUT_DIR_DEFAULT = str(RUNTIME_DIR / "output")
OUTPUT_FILENAME_TEMPLATE = os.environ.get(
    "OUTPUT_FILENAME_TEMPLATE", "{spider}_{date:%Y%m%d}.jsonl"
)

# Slack
SLACK_INCOMING_WEBHOOK_URL = os.environ.get("SLACK_INCOMING_WEBHOOK_URL", "")

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE_ENABLED = os.environ.get("LOG_FILE_ENABLED", "false").lower() == "true"
LOG_FILE_PATH = str(
    _resolve_project_path(
        os.environ.get("LOG_FILE_PATH", ""),
        RUNTIME_DIR / "logs" / "moneyforward_pk.log",
    )
)

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
