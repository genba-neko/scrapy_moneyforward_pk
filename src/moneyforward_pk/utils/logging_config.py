"""Common logging configuration for moneyforward_pk."""

from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_CONFIGURED_FLAG = "_moneyforward_pk_logging_configured"


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
        path = Path(
            log_file_path or os.environ.get("LOG_FILE_PATH", "moneyforward_pk.log")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = TimedRotatingFileHandler(
            path, when="midnight", backupCount=14, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        fh.setLevel(level)
        root.addHandler(fh)

    for noisy in ("boto3", "botocore", "urllib3", "s3transfer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    setattr(root, _CONFIGURED_FLAG, True)
