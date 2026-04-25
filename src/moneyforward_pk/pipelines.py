"""Scrapy pipelines for MoneyForward scraper.

Writes one JSON Lines file per spider under ``OUTPUT_DIR``. Replaces the
legacy DynamoDB pipeline per ``USER_DIRECTIVES.md``.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import IO, Any

from itemadapter import ItemAdapter

from moneyforward_pk.utils.paths import (
    ensure_unique_path,
    resolve_output_dir,
    resolve_output_path,
    sanitize_spider_name,
)

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = "{spider}_{date:%Y%m%d}.jsonl"
DEFAULT_RETENTION_DAYS = 14


class JsonOutputPipeline:
    """Append items to a per-spider JSON Lines file.

    The output directory is resolved from the ``OUTPUT_DIR`` setting (default
    ``runtime/output``) and is required to live inside ``PROJECT_ROOT``. The
    filename is rendered from ``OUTPUT_FILENAME_TEMPLATE`` (default
    ``{spider}_{date:%Y%m%d}.jsonl``). Existing files are not overwritten — a
    numeric suffix is appended on collision.
    """

    def __init__(
        self,
        output_dir: Path,
        template: str,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> None:
        self.output_dir = output_dir
        self.template = template
        self.retention_days = retention_days
        self._file: IO[str] | None = None
        self._path: Path | None = None
        self._count = 0

    @classmethod
    def from_crawler(cls, crawler) -> "JsonOutputPipeline":
        """Build a pipeline from Scrapy ``crawler.settings``."""
        settings = crawler.settings
        default_dir = Path(settings.get("OUTPUT_DIR_DEFAULT", "runtime/output"))
        output_dir = resolve_output_dir(settings.get("OUTPUT_DIR", ""), default_dir)
        template = settings.get("OUTPUT_FILENAME_TEMPLATE", DEFAULT_TEMPLATE)
        retention = settings.getint("OUTPUT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)
        return cls(output_dir=output_dir, template=template, retention_days=retention)

    def open_spider(self, spider) -> None:
        """Create the output directory, prune old files, and open the JSONL file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._prune_stale(spider)
        target = resolve_output_path(spider.name, self.output_dir, self.template)
        target = ensure_unique_path(target)
        self._path = target
        self._file = target.open("w", encoding="utf-8")
        spider.logger.info("JsonOutputPipeline open: path=%s", target)

    def _prune_stale(self, spider) -> None:
        """Remove this spider's output files older than ``retention_days``.

        Failure-safe: any unlink error is logged but does not abort the run.
        Files belonging to other spiders are left untouched (the prefix match
        uses the same sanitized spider name as the writer).
        """
        if self.retention_days <= 0:
            return
        cutoff = time.time() - self.retention_days * 86400
        prefix = sanitize_spider_name(spider.name) + "_"
        try:
            entries = list(self.output_dir.iterdir())
        except FileNotFoundError:
            return
        for entry in entries:
            if not entry.is_file() or not entry.name.startswith(prefix):
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    entry.unlink()
            except OSError as exc:
                spider.logger.debug("Retention skip %s: %s", entry, exc)

    def close_spider(self, spider) -> None:
        """Flush + close the file and stash the path/count in stats."""
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None
        crawler = getattr(spider, "crawler", None)
        stats = getattr(crawler, "stats", None) if crawler is not None else None
        if stats is not None and self._path is not None:
            stats.set_value(f"{spider.name}/output/path", str(self._path))
            stats.set_value(f"{spider.name}/output/items", self._count)

    def process_item(self, item: Any, spider) -> Any:
        """Serialize ``item`` as a single JSON Lines record."""
        if self._file is None:
            raise RuntimeError(
                "JsonOutputPipeline.process_item called before open_spider"
            )
        record = ItemAdapter(item).asdict()
        line = json.dumps(record, ensure_ascii=False, default=str)
        self._file.write(line)
        self._file.write("\n")
        self._count += 1
        return item
