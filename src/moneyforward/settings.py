"""Scrapy settings for moneyforward project."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_ROOT / "runtime"

# .env load (skip during pytest to preserve test-controlled env)
# Issue #44: ``override=True`` so .env is the source of truth. The PowerShell
# workbench profile (workbench/scripts/profile.ps1::Import-Env) injects .env
# values into the process env at terminal-start, but stale values persist when
# .env is edited without re-sourcing the profile. Without override=True,
# load_dotenv would respect those stale values and silently override the
# current .env contents.
if "pytest" not in sys.modules:
    load_dotenv(PROJECT_ROOT / ".env", override=True)


def _resolve_project_path(value: str | os.PathLike[str], default: Path) -> Path:
    """Resolve a possibly-relative path against PROJECT_ROOT."""
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


BOT_NAME = "moneyforward"

SPIDER_MODULES = ["moneyforward.spiders"]
NEWSPIDER_MODULE = "moneyforward.spiders"

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
    "moneyforward.middlewares.playwright_session.PlaywrightSessionMiddleware": 600,
    "scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware": 810,
}

# HTML inspector middleware — opt-in via env var (debug only). Stays enabled
# in DOWNLOADER_MIDDLEWARES at all times but its process_response is a no-op
# unless MONEYFORWARD_HTML_INSPECTOR is truthy. Env-driven so the flag flows
# through both Scrapy settings and standalone tooling.
MONEYFORWARD_HTML_INSPECTOR = os.environ.get(
    "MONEYFORWARD_HTML_INSPECTOR", "false"
).strip().lower() in {"1", "true", "yes", "on"}
MONEYFORWARD_HTML_INSPECTOR_DIR = os.environ.get("MONEYFORWARD_HTML_INSPECTOR_DIR", "")
MONEYFORWARD_RUNTIME_DIR = str(PROJECT_ROOT)
DOWNLOADER_MIDDLEWARES[
    "moneyforward.middlewares.html_inspector.HtmlInspectorMiddleware"
] = 590

ITEM_PIPELINES = {
    "moneyforward.pipelines.JsonArrayOutputPipeline": 300,
    "moneyforward.pipelines.DynamoDbPipeline": 400,
}

EXTENSIONS = {
    "moneyforward.extensions.slack_notifier_extension.SlackNotifierExtension": 500,
}

FEED_EXPORT_ENCODING = "utf-8"

# MoneyForward credentials / tunables
# Multi-account / per-site credentials live in config/accounts.yaml; the env
# vars below are a fallback for ad-hoc ``scrapy crawl <name>`` invocations.
SITE_LOGIN_USER = os.environ.get("SITE_LOGIN_USER", "")
SITE_LOGIN_PASS = os.environ.get("SITE_LOGIN_PASS", "")
SITE_PAST_MONTHS = int(os.environ.get("SITE_PAST_MONTHS", "12"))
MONEYFORWARD_LOGIN_MAX_RETRY = int(os.environ.get("MONEYFORWARD_LOGIN_MAX_RETRY", "2"))

# JSON output (replaces the legacy DynamoDB pipeline; USER_DIRECTIVES)
# Issue #40: aggregated 3-file JSON-array output (transaction / account /
# asset_allocation), not per-spider JSONL.
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "")

OUTPUT_DIR_DEFAULT = str(RUNTIME_DIR / "output")
OUTPUT_FILENAME_TEMPLATE = os.environ.get(
    "OUTPUT_FILENAME_TEMPLATE", "moneyforward_{spider_type}.json"
)

# DynamoDB output (Issue #67: parallel write alongside JSON)
# Table names are per spider_type; unset = that spider_type skips DynamoDB.
# All three unset = DynamoDbPipeline disables itself entirely (NotConfigured).
DYNAMODB_TABLE_NAME_TRANSACTION = os.environ.get("DYNAMODB_TABLE_NAME_TRANSACTION", "")
DYNAMODB_TABLE_NAME_ASSET_ALLOCATION = os.environ.get(
    "DYNAMODB_TABLE_NAME_ASSET_ALLOCATION", ""
)
DYNAMODB_TABLE_NAME_ACCOUNT = os.environ.get("DYNAMODB_TABLE_NAME_ACCOUNT", "")
DYNAMODB_PUT_DELAY = float(os.environ.get("DYNAMODB_PUT_DELAY", "3"))
DYNAMODB_BATCH_N = int(os.environ.get("DYNAMODB_BATCH_N", "10"))

# Slack
SLACK_INCOMING_WEBHOOK_URL = os.environ.get("SLACK_INCOMING_WEBHOOK_URL", "")

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE_ENABLED = os.environ.get("LOG_FILE_ENABLED", "false").lower() == "true"
LOG_FILE_PATH = str(
    _resolve_project_path(
        os.environ.get("LOG_FILE_PATH", ""),
        RUNTIME_DIR / "logs" / "moneyforward.log",
    )
)

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
