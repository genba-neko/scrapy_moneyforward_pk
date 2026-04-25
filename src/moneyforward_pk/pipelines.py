"""Scrapy pipelines for MoneyForward scraper.

Writes one JSON Lines file per spider under ``OUTPUT_DIR``. Replaces the
legacy DynamoDB pipeline per ``USER_DIRECTIVES.md``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import IO, Any

from itemadapter import ItemAdapter

from moneyforward_pk.utils.paths import (
    ensure_unique_path,
    resolve_output_dir,
    resolve_output_path,
)

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = "{spider}_{date:%Y%m%d}.jsonl"


class JsonOutputPipeline:
    """Append items to a per-spider JSON Lines file.

    The output directory is resolved from the ``OUTPUT_DIR`` setting (default
    ``runtime/output``) and is required to live inside ``PROJECT_ROOT``. The
    filename is rendered from ``OUTPUT_FILENAME_TEMPLATE`` (default
    ``{spider}_{date:%Y%m%d}.jsonl``). Existing files are not overwritten — a
    numeric suffix is appended on collision.
    """

    def __init__(self, output_dir: Path, template: str) -> None:
        self.output_dir = output_dir
        self.template = template
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
        return cls(output_dir=output_dir, template=template)

    def open_spider(self, spider) -> None:
        """Create the output directory and open the JSONL file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = resolve_output_path(spider.name, self.output_dir, self.template)
        target = ensure_unique_path(target)
        self._path = target
        self._file = target.open("w", encoding="utf-8")
        spider.logger.info("JsonOutputPipeline open: path=%s", target)

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
