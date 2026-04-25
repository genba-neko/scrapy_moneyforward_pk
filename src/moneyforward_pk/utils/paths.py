"""Output path helpers (project-rooted, sandbox-checked)."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_-]")


def sanitize_spider_name(name: str) -> str:
    """Return a filename-safe rendering of ``name``.

    Parameters
    ----------
    name : str
        Raw spider name. May contain characters that would break filename
        templating (``..``, path separators, NUL, etc.).

    Returns
    -------
    str
        ``name`` with every character outside ``[A-Za-z0-9_-]`` replaced by
        ``_``. An empty result falls back to ``"spider"`` so downstream code
        always receives a non-empty token.
    """
    if not name:
        return "spider"
    sanitized = _SAFE_NAME_RE.sub("_", name)
    return sanitized or "spider"


def resolve_output_dir(value: str | os.PathLike[str] | None, default: Path) -> Path:
    """Resolve ``OUTPUT_DIR`` against PROJECT_ROOT and verify sandbox.

    Parameters
    ----------
    value : str | PathLike | None
        Configured output directory (relative or absolute).
    default : Path
        Fallback if ``value`` is empty.

    Returns
    -------
    Path
        Absolute resolved directory under PROJECT_ROOT.

    Raises
    ------
    ValueError
        When the resolved path escapes PROJECT_ROOT (path traversal guard).
    """
    if not value:
        path = default
    else:
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
    resolved = path.resolve()
    project_root = PROJECT_ROOT.resolve()
    if not resolved.is_relative_to(project_root):
        raise ValueError(
            f"OUTPUT_DIR must stay under PROJECT_ROOT ({project_root}); got {resolved}"
        )
    return resolved


def resolve_output_path(
    spider_name: str,
    output_dir: Path,
    template: str,
    today: date | None = None,
) -> Path:
    """Render the per-spider output file path.

    Parameters
    ----------
    spider_name : str
        Scrapy spider name; used as ``{spider}`` in ``template``.
    output_dir : Path
        Already-resolved directory (see ``resolve_output_dir``).
    template : str
        Filename template; supports ``{spider}`` and ``{date:%Y%m%d}`` style fields.
    today : date | None
        Date injection for tests. Defaults to ``date.today()``.

    Returns
    -------
    Path
        Absolute output file path under ``output_dir``.
    """
    today = today or date.today()
    safe_spider = sanitize_spider_name(spider_name)
    filename = template.format(spider=safe_spider, date=today)
    return output_dir / filename


def ensure_unique_path(path: Path) -> Path:
    """Append ``-1``/``-2``/... suffix if ``path`` already exists.

    Parameters
    ----------
    path : Path
        Desired output path.

    Returns
    -------
    Path
        A path that does not yet exist on disk.
    """
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    i = 1
    while True:
        candidate = parent / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1
