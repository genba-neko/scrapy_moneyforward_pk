"""Alt-credential resolution and login_attempt dispatch (iter3 T1)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

from scrapy.http import Request

from moneyforward_pk.spiders.base.moneyforward_base import (
    MoneyforwardBase,
    XMoneyforwardLoginMixin,
)


class _StubSpider(MoneyforwardBase):
    name = "mf_alt_test"


def _build_spider(
    *,
    user: str = "primary@example.com",
    password: str = "primary-pw",  # noqa: S107 — fixture credential
    alt_user: str = "",
    alt_pass: str = "",
) -> _StubSpider:
    spider = _StubSpider(login_user=user, login_pass=password)
    spider.login_alt_user = alt_user
    spider.login_alt_pass = alt_pass
    crawler = MagicMock()
    crawler.stats = MagicMock()
    spider.crawler = crawler
    return spider


def test_resolve_credentials_returns_primary_on_attempt_zero():
    spider = _build_spider(alt_user="alt@example.com", alt_pass="alt-pw")  # noqa: S106
    user, password = spider._resolve_credentials(0)
    assert user == "primary@example.com"
    assert password == "primary-pw"


def test_resolve_credentials_returns_alt_on_retry_when_configured():
    spider = _build_spider(alt_user="alt@example.com", alt_pass="alt-pw")  # noqa: S106
    user, password = spider._resolve_credentials(1)
    assert user == "alt@example.com"
    assert password == "alt-pw"


def test_resolve_credentials_falls_back_to_primary_when_alt_missing():
    spider = _build_spider(alt_user="", alt_pass="")
    user, password = spider._resolve_credentials(2)
    assert user == "primary@example.com"
    assert password == "primary-pw"


def test_resolve_credentials_requires_both_alt_fields():
    """Half-configured alt (only user, no pass) must not engage."""
    spider = _build_spider(alt_user="alt@example.com", alt_pass="")
    user, password = spider._resolve_credentials(1)
    assert user == "primary@example.com"


def test_build_login_request_carries_login_attempt_meta():
    spider = _build_spider()
    req = spider._build_login_request(login_attempt=2)
    assert req.meta["moneyforward_login_attempt"] == 2


def test_build_login_request_default_attempt_zero():
    spider = _build_spider()
    req = spider._build_login_request()
    assert req.meta["moneyforward_login_attempt"] == 0


def test_handle_force_login_propagates_login_retry_times_to_attempt():
    spider = _build_spider(alt_user="alt@example.com", alt_pass="alt-pw")  # noqa: S106
    retry = Request(
        url="https://moneyforward.com/cf",
        meta={"moneyforward_force_login": True, "login_retry_times": 1},
    )
    login_req = spider.handle_force_login(retry)
    assert login_req.meta["moneyforward_login_attempt"] == 1
    # alt counter must fire when alt creds are configured + retry path engages
    stats = cast(MagicMock, cast(Any, spider.crawler).stats)
    stats.inc_value.assert_any_call(f"{spider.name}/login/alt_user_used", count=1)


def test_handle_force_login_skips_alt_counter_when_alt_unset():
    spider = _build_spider()  # no alt configured
    retry = Request(
        url="https://moneyforward.com/cf",
        meta={"moneyforward_force_login": True, "login_retry_times": 1},
    )
    spider.handle_force_login(retry)
    stats = cast(MagicMock, cast(Any, spider.crawler).stats)
    calls = [c.args for c in stats.inc_value.call_args_list]
    assert (f"{spider.name}/login/alt_user_used",) not in calls


def test_xmoneyforward_mixin_uses_resolve_credentials_when_present():
    """XMoneyforwardLoginMixin must consult _resolve_credentials when the
    composing spider provides one (i.e. inherits MoneyforwardBase)."""

    class _Combined(XMoneyforwardLoginMixin, _StubSpider):
        name = "xmf_alt_test"

    spider = _Combined(login_user="primary@example.com", login_pass="pw")  # noqa: S106
    spider.login_alt_user = "alt@example.com"
    spider.login_alt_pass = "alt-pw"
    user, password = spider._resolve_credentials(1)
    assert user == "alt@example.com"
    assert password == "alt-pw"


def test_from_crawler_loads_alt_credentials_from_settings():
    crawler = MagicMock()
    crawler.settings.get.side_effect = lambda key, default=None: {
        "SITE_LOGIN_USER": "primary@example.com",
        "SITE_LOGIN_PASS": "pw",
        "SITE_LOGIN_ALT_USER": "alt@example.com",
        "SITE_LOGIN_ALT_PASS": "alt-pw",
    }.get(key, default)
    spider = _StubSpider.from_crawler(crawler)
    assert spider.login_alt_user == "alt@example.com"
    assert spider.login_alt_pass == "alt-pw"


def test_from_crawler_handles_missing_alt_credentials_gracefully():
    crawler = MagicMock()
    crawler.settings.get.side_effect = lambda key, default=None: {
        "SITE_LOGIN_USER": "primary@example.com",
        "SITE_LOGIN_PASS": "pw",
    }.get(key, default)
    spider = _StubSpider.from_crawler(crawler)
    assert spider.login_alt_user == ""
    assert spider.login_alt_pass == ""
