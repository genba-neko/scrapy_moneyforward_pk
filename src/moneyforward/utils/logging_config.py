"""Common logging configuration for moneyforward."""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from moneyforward.utils.log_filter import attach_sensitive_filter

_CONFIGURED_FLAG = "_moneyforward_logging_configured"


def setup_common_logging(
    *,
    log_level: str | None = None,
    log_file_enabled: bool | None = None,
    log_file_path: str | os.PathLike[str] | None = None,
) -> None:
    """Idempotent logger setup: console + optional rotating file."""
    root = logging.getLogger()
    if getattr(root, _CONFIGURED_FLAG, False):
        return

    level_name = (log_level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(level)
    root.addHandler(console)

    enabled = (
        log_file_enabled
        if log_file_enabled is not None
        else os.environ.get("LOG_FILE_ENABLED", "false").lower() == "true"
    )
    if enabled:
        raw = log_file_path or os.environ.get("LOG_FILE_PATH", "moneyforward.log")
        path = Path(raw)
        if not path.is_absolute():
            # Resolve against project root (src/moneyforward/utils/ → 3 levels up)
            project_root = Path(__file__).resolve().parents[3]
            path = project_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = TimedRotatingFileHandler(
            path, when="midnight", backupCount=14, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        fh.setLevel(level)
        root.addHandler(fh)

    for noisy in ("urllib3", "asyncio", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Sensitive-data redaction: attach to root + scrapy + project loggers so
    # any handler downstream sees a scrubbed record. Idempotent.
    for name in ("", "scrapy", "moneyforward"):
        attach_sensitive_filter(logging.getLogger(name))

    setattr(root, _CONFIGURED_FLAG, True)
