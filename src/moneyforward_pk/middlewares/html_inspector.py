"""Opt-in middleware that dumps response HTML for offline inspection.

Activated only when ``MONEYFORWARD_HTML_INSPECTOR=true`` is set (env or
Scrapy setting). Off by default so production runs and the existing test
suite see no behavioural change. Dumps land in
``runtime/inspect/{spider}_{YYYYmmddHHMMSS}_{seq}.html`` so successive
requests on a single spider run never collide.

This restores the legacy ``scrapy_moneyforward`` HTML-debug capability
that was lost during the Playwright rebuild.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from moneyforward_pk.utils.paths import sanitize_spider_name

logger = logging.getLogger(__name__)

_DEFAULT_SUBDIR = "inspect"
_TS_FORMAT = "%Y%m%d%H%M%S"


def _is_truthy(value: object) -> bool:
    """Return True when ``value`` looks like an enabling flag."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class HtmlInspectorMiddleware:
    """Persist response HTML to disk when explicitly enabled.

    Parameters
    ----------
    output_dir : Path
        Directory under which dumps are written. Created on first use.
    enabled : bool
        Master switch. When False, ``process_response`` is a no-op.
    """

    def __init__(self, output_dir: Path, *, enabled: bool) -> None:
        self.output_dir = output_dir
        self.enabled = enabled
        self._seq = 0

    @classmethod
    def from_crawler(cls, crawler) -> "HtmlInspectorMiddleware":
        """Build the middleware from Scrapy settings (env-overridable)."""
        settings = crawler.settings
        enabled = _is_truthy(settings.get("MONEYFORWARD_HTML_INSPECTOR", False))
        runtime_dir = Path(
            settings.get("MONEYFORWARD_RUNTIME_DIR")
            or settings.get("PROJECT_ROOT", ".")
        )
        custom_dir = settings.get("MONEYFORWARD_HTML_INSPECTOR_DIR", "")
        if custom_dir:
            output_dir = Path(custom_dir)
            if not output_dir.is_absolute():
                output_dir = runtime_dir / output_dir
        else:
            output_dir = runtime_dir / "runtime" / _DEFAULT_SUBDIR
        return cls(output_dir=output_dir, enabled=enabled)

    def process_response(self, request, response, spider):
        """Dump ``response.body`` when enabled, then pass the response on."""
        if not self.enabled:
            return response
        body = getattr(response, "body", None)
        if not body:
            return response
        try:
            self._dump(spider, response)
        except OSError as exc:  # disk full / permissions / locked file
            spider.logger.debug("HtmlInspector skip: %s", exc)
        return response

    def _dump(self, spider, response) -> None:
        """Write the response HTML to a unique path under ``output_dir``."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._seq += 1
        spider_name = sanitize_spider_name(getattr(spider, "name", "spider"))
        ts = time.strftime(_TS_FORMAT)
        slug = _slugify_url(getattr(response, "url", ""))
        suffix = f"_{slug}" if slug else ""
        target = self.output_dir / f"{spider_name}_{ts}_{self._seq:04d}{suffix}.html"
        body = response.body
        if isinstance(body, str):
            target.write_text(body, encoding="utf-8")
        else:
            target.write_bytes(body)
        spider.logger.debug("HtmlInspector dump: %s", target)


def _slugify_url(url: str) -> str:
    """Reduce a URL to a short filesystem-safe slug (max 40 chars)."""
    if not url:
        return ""
    slug = re.sub(r"^https?://", "", url)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", slug).strip("_")
    return slug[:40]
