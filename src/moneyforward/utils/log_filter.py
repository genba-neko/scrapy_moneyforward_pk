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
    r"([?&](?:auth|token|access_token|refresh_token|id_token|session|sessionid|"
    r"sid|jwt|api_key|apikey|client_secret|secret|otp|code|signature|sig|"
    r"x-amz-signature|x-amz-credential|x-amz-security-token|key)=)[^&\s\"']+",
    re.IGNORECASE,
)
_COOKIE_HEADER = re.compile(
    r"((?:set-)?cookie):\s*[^\r\n]+",
    re.IGNORECASE,
)
# Bearer / Basic / Digest / Token / arbitrary scheme — redact the entire value.
_AUTH_HEADER = re.compile(
    r"(authorization|proxy-authorization):\s*[^\r\n]+",
    re.IGNORECASE,
)
# Common sensitive header names (X-Api-Key, X-Auth-Token, etc.).
_SENSITIVE_HEADER = re.compile(
    r"(x-(?:api-key|auth-token|csrf-token|xsrf-token|access-token|"
    r"refresh-token|session-token|secret)|api-key|csrf-token|xsrf-token):"
    r"\s*[^\r\n]+",
    re.IGNORECASE,
)
_PASSWORD_KV = re.compile(
    r"((?:password|passwd|pwd|secret|api_key|apikey|access_token|"
    r"refresh_token|client_secret)\s*[=:]\s*)[^\s,;&\"']+",
    re.IGNORECASE,
)
# JSON-style sensitive value: "password": "abc" / 'token': 'xyz'
_JSON_SENSITIVE_KV = re.compile(
    r"(['\"](?:password|passwd|pwd|token|access_token|refresh_token|"
    r"api_key|apikey|secret|client_secret|authorization)['\"]"
    r"\s*:\s*['\"])[^'\"]+(['\"])",
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
    text = _SENSITIVE_HEADER.sub(rf"\1: {_REDACTED}", text)
    text = _JSON_SENSITIVE_KV.sub(rf"\1{_REDACTED}\2", text)
    text = _PASSWORD_KV.sub(rf"\1{_REDACTED}", text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Redact URL queries / cookies / auth headers / password kv pairs.

    Pre-formats the record via getMessage() before scrubbing so that
    msg/args placeholders are already resolved. This prevents TypeError
    when a pattern (e.g. _PASSWORD_KV) consumes a %s placeholder in msg
    while args still holds the corresponding value.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        """Apply redaction to the record and always return True."""
        try:
            raw = record.getMessage()
        except Exception:
            raw = str(record.msg)
        record.msg = _scrub(raw)
        record.args = None
        return True


def attach_sensitive_filter(target: logging.Filterer) -> None:
    """Idempotently attach a ``SensitiveDataFilter`` to a logger or handler."""
    if any(isinstance(f, SensitiveDataFilter) for f in target.filters):
        return
    target.addFilter(SensitiveDataFilter())
