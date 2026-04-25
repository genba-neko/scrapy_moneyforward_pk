"""Sensitive-data redaction filter for the project loggers.

Designed for ``logger.exception`` paths where Playwright traces or Scrapy
``request.headers`` may render full URLs (with ``auth=``/``token=``
queries), ``Cookie``/``Set-Cookie`` headers, or ``Authorization`` bearer
tokens into log records. Attaching this filter idempotently in
``setup_common_logging`` ensures the same redaction policy applies to
every handler downstream.
"""

from __future__ import annotations

import logging
import re

# Patterns are intentionally narrow to avoid masking unrelated content.
# Order matters: query-string scrubbing runs before generic URL masking so
# the ``auth=``/``token=`` value (sensitive) is consumed before the host
# token (low-signal but useful for debugging) gets replaced.
_URL_QUERY_REDACT = re.compile(
    r"([?&](?:auth|token|access_token|api_key|apikey)=)[^&\s\"']+",
    re.IGNORECASE,
)
_COOKIE_HEADER = re.compile(
    r"((?:set-)?cookie):\s*[^\r\n]+",
    re.IGNORECASE,
)
_AUTH_HEADER = re.compile(
    r"(authorization):\s*[^\r\n]+",
    re.IGNORECASE,
)
_PASSWORD_KV = re.compile(
    r"((?:password|passwd|pwd)\s*[=:]\s*)[^\s,;&\"']+",
    re.IGNORECASE,
)

_REDACTED = "[REDACTED]"


def _scrub(text: str) -> str:
    """Apply all redaction patterns to ``text`` and return the result."""
    if not text:
        return text
    text = _URL_QUERY_REDACT.sub(rf"\1{_REDACTED}", text)
    text = _COOKIE_HEADER.sub(rf"\1: {_REDACTED}", text)
    text = _AUTH_HEADER.sub(rf"\1: {_REDACTED}", text)
    text = _PASSWORD_KV.sub(rf"\1{_REDACTED}", text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Redact URL queries / cookies / auth headers / password kv pairs.

    Mutates ``record.msg`` and string elements of ``record.args`` in place
    before the formatter is invoked. Non-string args (ints, dicts, ...) are
    left untouched.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        """Apply redaction to the record and always return True."""
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        args = record.args
        if isinstance(args, tuple) and args:
            new_args: list[object] = []
            mutated = False
            for arg in args:
                if isinstance(arg, str):
                    scrubbed = _scrub(arg)
                    new_args.append(scrubbed)
                    if scrubbed is not arg:
                        mutated = True
                else:
                    new_args.append(arg)
            if mutated:
                record.args = tuple(new_args)
        elif isinstance(args, dict):
            record.args = {
                k: (_scrub(v) if isinstance(v, str) else v) for k, v in args.items()
            }
        return True


def attach_sensitive_filter(logger: logging.Logger) -> None:
    """Idempotently attach a ``SensitiveDataFilter`` to a logger."""
    if any(isinstance(f, SensitiveDataFilter) for f in logger.filters):
        return
    logger.addFilter(SensitiveDataFilter())
