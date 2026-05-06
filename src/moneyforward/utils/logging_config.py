"""Common logging configuration for moneyforward."""

from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from moneyforward.utils.log_filter import attach_sensitive_filter

_CONFIGURED_FLAG = "_moneyforward_logging_configured"

_axiom_lock = threading.Lock()
_UNSET = object()
_axiom_handler: logging.Handler | None | object = _UNSET


def _resolve_axiom_key(key: str) -> str:
    try:
        from moneyforward.secrets import resolver
        from moneyforward.secrets.exceptions import SecretNotFound

        try:
            return resolver.get(key).strip()
        except SecretNotFound:
            pass
    except Exception:
        pass
    return (os.getenv(key) or "").strip()


def _build_axiom_handler() -> logging.Handler | None:
    token = _resolve_axiom_key("AXIOM_TOKEN")
    org_id = _resolve_axiom_key("AXIOM_ORG_ID")
    if not (token and org_id):
        return None
    dataset = os.getenv("AXIOM_DATASET", "moneyforward-crawler")
    try:
        from axiom_py import Client  # type: ignore[import]
        from axiom_py.logging import AxiomHandler  # type: ignore[import]
    except ImportError:
        return None
    try:
        client = Client(token=token, org_id=org_id)
        handler = AxiomHandler(client=client, dataset=dataset)
        handler.setLevel(logging.INFO)
        return handler
    except Exception as e:
        print(f"[axiom] handler init failed: {e!r}", file=sys.stderr)
        return None


def _get_axiom_handler() -> logging.Handler | None:
    global _axiom_handler
    with _axiom_lock:
        if _axiom_handler is _UNSET:
            _axiom_handler = _build_axiom_handler()
    return _axiom_handler  # type: ignore[return-value]


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

    ax = _get_axiom_handler()
    if ax is not None:
        root.addHandler(ax)

    for noisy in ("urllib3", "asyncio", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Sensitive-data redaction on each handler so all records — including those
    # propagated from child loggers — are scrubbed before reaching any output.
    for handler in root.handlers:
        attach_sensitive_filter(handler)

    setattr(root, _CONFIGURED_FLAG, True)
