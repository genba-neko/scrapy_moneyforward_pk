"""Opt-in middleware that dumps response HTML for offline inspection.

Activated only when ``MONEYFORWARD_HTML_INSPECTOR=true`` is set (env or
Scrapy setting). Off by default so production runs see no behavioural change.

Output structure::

    runtime/inspect/{YYYYMMDD_HHMMSS}_{spider}/
    ├── flow.log                    # navigation sequence (JSONL)
    ├── accounts/
    │   ├── 001_show.html
    │   └── 002_edit.html
    └── transactions/
        └── 003_index.html

HTTP 4xx/5xx responses get an ``_error`` suffix. Playwright internal
navigations are captured via ``page.on("load")``.
"""

from __future__ import annotations

import json
import logging
import shlex
import sys
import weakref
from datetime import datetime
from pathlib import Path
from typing import IO
from urllib.parse import urlparse

from scrapy import signals

from moneyforward.utils.paths import sanitize_spider_name

logger = logging.getLogger(__name__)


def _is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _extract_sub_path(url: str) -> str:
    """Map URL path to a filesystem sub-path, removing traversal segments."""
    path = urlparse(url).path.strip("/")
    safe_parts = [p for p in path.split("/") if p and p != ".."]
    return "/".join(safe_parts) or "index"


class HtmlInspectorMiddleware:
    """Persist response HTML to disk when explicitly enabled.

    Parameters
    ----------
    output_dir : Path
        Base directory under which per-run subdirectories are created.
    enabled : bool
        Master switch. When False, ``process_response`` is a no-op.
    """

    def __init__(self, output_dir: Path, *, enabled: bool) -> None:
        self.output_dir = output_dir
        self.enabled = enabled
        self.run_dir = output_dir
        self._seq = 0
        self._flow_fh: IO[str] | None = None
        self._playwright_pages: weakref.WeakSet[object] = weakref.WeakSet()

    @classmethod
    def from_crawler(cls, crawler) -> "HtmlInspectorMiddleware":
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
                output_dir = runtime_dir / custom_dir
        else:
            output_dir = runtime_dir / "runtime" / "inspect"
        inst = cls(output_dir=output_dir, enabled=enabled)
        if enabled:
            crawler.signals.connect(inst.spider_opened, signal=signals.spider_opened)
            crawler.signals.connect(inst.spider_closed, signal=signals.spider_closed)
        return inst

    # ------------------------------------------------------------------
    # Spider signals
    # ------------------------------------------------------------------

    def spider_opened(self, spider) -> None:
        self._seq = 0
        self._playwright_pages = weakref.WeakSet()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        spider_name = sanitize_spider_name(getattr(spider, "name", "spider"))
        self.run_dir = self.output_dir / f"{ts}_{spider_name}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._flow_fh = (self.run_dir / "flow.log").open("w", encoding="utf-8")
        meta = {
            "type": "meta",
            "spider": spider_name,
            "command": shlex.join(sys.argv),
            "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._flow_fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
        self._flow_fh.flush()
        logger.debug("HtmlInspector: started. output=%s", self.run_dir)

    def spider_closed(self, spider) -> None:
        if self._flow_fh:
            self._flow_fh.close()
            self._flow_fh = None
        logger.debug("HtmlInspector: finished. output=%s", self.run_dir)

    # ------------------------------------------------------------------
    # Scrapy middleware interface
    # ------------------------------------------------------------------

    def process_response(self, request, response):
        if not self.enabled:
            return response
        # Require spider_opened to have been called (run_dir and flow.log ready).
        if self._flow_fh is None:
            return response
        body = getattr(response, "body", None)
        if not body:
            return response
        try:
            html = (
                response.text
                if hasattr(response, "text")
                else body.decode("utf-8", errors="replace")
            )
            status = getattr(response, "status", 200)
            callback = getattr(request.callback, "__name__", None)
            self._save(html, response.url, status=status, callback=callback)
            page = request.meta.get("playwright_page")
            if page is not None:
                self._attach_playwright_listener(page, callback=callback)
        except Exception as exc:  # noqa: BLE001
            logger.warning("HtmlInspector skip: %s", exc)
        return response

    # ------------------------------------------------------------------
    # Playwright listener
    # ------------------------------------------------------------------

    def _attach_playwright_listener(self, page, callback: str | None = None) -> None:
        if page in self._playwright_pages:
            return
        self._playwright_pages.add(page)
        inspector = self
        load_callback = f"{callback}->load" if callback else "playwright->load"

        async def on_load() -> None:
            try:
                url = page.url
                html = await page.content()
                inspector._save(html, url, status=200, callback=load_callback)
            except Exception as exc:  # noqa: BLE001
                logger.warning("HtmlInspector: load handler error: %s", exc)

        page.on("load", on_load)

    # ------------------------------------------------------------------
    # Core save logic
    # ------------------------------------------------------------------

    def _save(
        self, html: str, url: str, *, status: int = 200, callback: str | None = None
    ) -> None:
        parsed = urlparse(url)
        is_error = status >= 400
        sub_path = _extract_sub_path(url)
        self._seq += 1
        filepath = self._resolve_filepath(sub_path, is_error)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(html, encoding="utf-8")
        self._append_flow(parsed.query, sub_path, filepath, is_error, callback=callback)
        logger.debug("HtmlInspector dump: %s", filepath)

    def _resolve_filepath(self, sub_path: str, is_error: bool) -> Path:
        parts = sub_path.rsplit("/", 1)
        dir_part = parts[0] if len(parts) == 2 else ""
        name = parts[-1] or "index"
        seq = f"{self._seq:03d}"
        filename = f"{seq}_{name}_error.html" if is_error else f"{seq}_{name}.html"
        return self.run_dir / dir_part / filename

    def _append_flow(
        self,
        query: str,
        path: str,
        filepath: Path,
        is_error: bool,
        *,
        callback: str | None = None,
    ) -> None:
        if self._flow_fh is None:
            return
        entry: dict[str, object] = {
            "seq": self._seq,
            "time": datetime.now().strftime("%H:%M:%S"),
            "callback": callback or "",
            "path": path,
            "file": str(filepath.relative_to(self.run_dir)).replace("\\", "/"),
            "error": is_error,
            "query": query,
        }
        self._flow_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._flow_fh.flush()
