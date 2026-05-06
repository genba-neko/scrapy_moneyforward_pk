"""Scrapy pipelines for MoneyForward scraper.

Writes items to **3 aggregated JSON-array files** keyed by spider type
(transaction / account / asset_allocation). All sites and accounts append
into the same file per type, matching the original PJ output contract.

The crawl_runner is responsible for:
- truncating the 3 files (writing ``[``) before run_all begins
- closing the 3 files (appending ``]``) after run_all ends

Each spider invocation appends its items between an open ``[`` and the
final ``]``, separated by ``,`` so that the resulting file is a valid
JSON array (i.e. ``json.load(f)`` succeeds).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import IO, Any

from itemadapter import ItemAdapter

from moneyforward.utils.paths import resolve_output_dir

logger = logging.getLogger(__name__)

DEFAULT_FILENAME_TEMPLATE = "moneyforward_{spider_type}.json"


class JsonArrayOutputPipeline:
    """Append items to ``moneyforward_{spider_type}.json`` as JSON-array entries.

    Notes
    -----
    Coordination with ``crawl_runner`` is required:

    1. Before ``run_all`` starts, crawl_runner truncates each output file
       and writes ``[`` (one byte). See ``initialize_output_files`` in
       ``_runner_core``.
    2. While spiders run, this pipeline appends items separated by ``,``.
    3. After ``run_all`` ends, crawl_runner appends ``]`` to each file.

    A single-shot ``scrapy crawl <name>`` invocation (without crawl_runner)
    will produce a non-closed file ending without ``]``; that mode is
    out-of-scope for the new pipeline contract.
    """

    def __init__(self, output_dir: Path, template: str) -> None:
        self.output_dir = output_dir
        self.template = template
        self._file: IO[str] | None = None
        self._path: Path | None = None
        self._wrote_first_in_run = False
        self.crawler: Any = None
        self._spider_name: str = ""

    @classmethod
    def from_crawler(cls, crawler) -> "JsonArrayOutputPipeline":
        """Build a pipeline from ``crawler.settings``."""
        settings = crawler.settings
        default_dir = Path(settings.get("OUTPUT_DIR_DEFAULT", "runtime/output"))
        output_dir = resolve_output_dir(settings.get("OUTPUT_DIR", ""), default_dir)
        template = settings.get("OUTPUT_FILENAME_TEMPLATE", DEFAULT_FILENAME_TEMPLATE)
        instance = cls(output_dir=output_dir, template=template)
        instance.crawler = crawler
        return instance

    def open_spider(self) -> None:
        """Open the per-spider-type file in append mode."""
        spider = self.crawler.spider
        spider_type = getattr(spider, "spider_type", spider.name)
        self._spider_name = spider.name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Issue #40 changed output to a fixed-name 3-file aggregate. If the
        # template does not reference ``{spider_type}``, the configured value
        # is from a pre-#40 ``.env`` and would land outside the orchestrator's
        # initialize/finalize bracket-management. Force the default in that
        # case and warn the operator instead of producing broken JSON files.
        template = self.template
        if "{spider_type}" not in template:
            logger.warning(
                "OUTPUT_FILENAME_TEMPLATE %r is incompatible with Issue #40; "
                "falling back to %r. Update .env to silence this warning.",
                template,
                DEFAULT_FILENAME_TEMPLATE,
            )
            template = DEFAULT_FILENAME_TEMPLATE
        target = self.output_dir / template.format(spider_type=spider_type)
        self._path = target
        # If file is missing or empty, initialize it as ``[``. Normally the
        # orchestrator does this, but a standalone ``scrapy crawl`` call
        # should still produce a parseable (though non-finalized) file.
        if not target.exists() or target.stat().st_size == 0:
            target.write_text("[", encoding="utf-8")
        # Decide whether the next item is the first of the current array.
        # Size > 1 means the file already contains at least one item from
        # an earlier invocation, so we need to emit a leading ``,``.
        size = target.stat().st_size
        self._wrote_first_in_run = size > 1
        self._file = target.open("a", encoding="utf-8")
        logger.info("JsonArrayOutputPipeline open: path=%s", target)

    def process_item(self, item: Any) -> Any:
        """Serialize ``item`` and append to the JSON array."""
        if self._file is None:
            raise RuntimeError(
                "JsonArrayOutputPipeline.process_item called before open_spider"
            )
        record = ItemAdapter(item).asdict()
        item_json = json.dumps(record, ensure_ascii=False, default=str, indent=2)
        indented = "  " + item_json.replace("\n", "\n  ")
        separator = ",\n" if self._wrote_first_in_run else "\n"
        self._file.write(separator + indented)
        self._wrote_first_in_run = True
        return item

    def close_spider(self) -> None:
        """Flush + close. Note: closing ``]`` is written by the runner."""
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None
        if self.crawler is not None and self._path is not None and self._spider_name:
            self.crawler.stats.set_value(
                f"{self._spider_name}/output/path", str(self._path)
            )
