"""Session helpers (login-state detection)."""

from __future__ import annotations

import re

# When MoneyForward kicks you back to /sign_in the URL contains these paths.
_LOGIN_URL_PATTERNS = [
    re.compile(r"/sign_in(?:$|[/?])"),
    re.compile(r"/users/sign_in(?:$|[/?])"),
]


def is_login_url(url: str) -> bool:
    return any(p.search(url) for p in _LOGIN_URL_PATTERNS)


def is_session_expired(response) -> bool:
    """Best-effort session-expiry detection from a Scrapy response."""
    if is_login_url(response.url):
        return True
    title = response.css("title::text").get(default="")
    if "ログイン" in title or "sign in" in title.lower():
        return True
    return False
