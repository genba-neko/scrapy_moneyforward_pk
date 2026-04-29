"""Verify login_flow selectors against the saved DOM fixtures.

Fixtures live under ``data/fixutres_source/`` and were captured from real
MoneyForward partner-portal pages (xmf_ssnb). Each test asserts that the
CSS selector used by ``MoneyforwardBase.login_flow`` /
``XMoneyforwardLoginMixin.login_flow`` actually finds the expected element
in the saved HTML — so the spider doesn't silently skip a click and end up
trying to fill a form that isn't on the page.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "data" / "fixutres_source"

# The saved fixtures are all from xmf_ssnb (partner portal).
TOP_PAGE_HTML = FIXTURE_ROOT / "01. トップページ" / "x_moneyforward.html"
LOGIN_PAGE_HTML = FIXTURE_ROOT / "02. ログインページ" / "x_moneyforward_sigin_in.html"
LOGGED_IN_HTML = FIXTURE_ROOT / "03. ログイン後ページ" / "x_moneyforward_home.html"


def _response(path: Path, url: str) -> HtmlResponse:
    body = path.read_bytes()
    return HtmlResponse(
        url=url,
        body=body,
        encoding="utf-8",
        request=Request(url=url),
    )


# --------------------------------------------------------------- selectors


@pytest.mark.skipif(not TOP_PAGE_HTML.exists(), reason="fixture missing")
def test_top_page_login_link_selector_matches():
    """Issue #43: ``a[href$="/users/sign_in"]`` must find the login link.

    Pre-fix the spider used ``a[href="/users/sign_in"]`` (exact match)
    which silently skipped because the saved markup uses the absolute URL
    ``href="https://ssnb.x.moneyforward.com/users/sign_in"``.
    """
    resp = _response(TOP_PAGE_HTML, "https://ssnb.x.moneyforward.com/")
    # Suffix match (the new selector).
    new = resp.css('a[href$="/users/sign_in"]')
    assert new, "login link not found by the new suffix-match selector"
    href = new.attrib.get("href", "")
    assert href.endswith("/users/sign_in")
    assert "ログイン" in (new.css("::text").get() or "")
    # Old (broken) exact-match selector should not match.
    old = resp.css('a[href="/users/sign_in"]')
    assert not old, "old exact-match selector unexpectedly matched"


@pytest.mark.skipif(not LOGIN_PAGE_HTML.exists(), reason="fixture missing")
def test_login_page_email_input_selector_matches():
    """Email input uses ``name="sign_in_session_service[email]"`` (variant form name)."""
    resp = _response(LOGIN_PAGE_HTML, "https://ssnb.x.moneyforward.com/users/sign_in")
    field = resp.css('input[name="sign_in_session_service[email]"]')
    assert field, "email input not found"
    assert field.attrib.get("type") == "email"


@pytest.mark.skipif(not LOGIN_PAGE_HTML.exists(), reason="fixture missing")
def test_login_page_password_input_selector_matches():
    """Password input is on the same page (1-page form for partner portal)."""
    resp = _response(LOGIN_PAGE_HTML, "https://ssnb.x.moneyforward.com/users/sign_in")
    field = resp.css('input[name="sign_in_session_service[password]"]')
    assert field, "password input not found"
    assert field.attrib.get("type") == "password"


@pytest.mark.skipif(not LOGIN_PAGE_HTML.exists(), reason="fixture missing")
def test_login_page_submit_button_selector_matches():
    resp = _response(LOGIN_PAGE_HTML, "https://ssnb.x.moneyforward.com/users/sign_in")
    # The login form's submit button is identified by value="ログイン" so it is
    # not confused with the signup form's submit (value="新規登録").
    submit = resp.css('input[type="submit"][value="ログイン"]')
    assert submit, "submit button not found"


# --------------------------------------------------------------- session detection


@pytest.mark.skipif(not LOGGED_IN_HTML.exists(), reason="fixture missing")
def test_logged_in_page_has_logout_link():
    """``_is_logged_in_page`` heuristic: ``a[href*="/sign_out"]`` exists."""
    resp = _response(LOGGED_IN_HTML, "https://ssnb.x.moneyforward.com/")
    logout = resp.css('a[href*="/sign_out"]')
    assert logout, "logout link missing on logged-in page"


@pytest.mark.skipif(not TOP_PAGE_HTML.exists(), reason="fixture missing")
def test_top_page_has_no_logout_link():
    """Anonymous top page must not match the logout selector (otherwise
    ``_is_logged_in_page`` would falsely skip login_flow on first run)."""
    resp = _response(TOP_PAGE_HTML, "https://ssnb.x.moneyforward.com/")
    logout = resp.css('a[href*="/sign_out"]')
    assert not logout, "anonymous top page unexpectedly contains a logout link"


# --------------------------------------------------------------- session_utils


@pytest.mark.skipif(not LOGIN_PAGE_HTML.exists(), reason="fixture missing")
def test_is_session_expired_true_on_login_page():
    from moneyforward_pk.utils.session_utils import is_session_expired

    resp = _response(LOGIN_PAGE_HTML, "https://ssnb.x.moneyforward.com/users/sign_in")
    assert is_session_expired(resp) is True


@pytest.mark.skipif(not LOGGED_IN_HTML.exists(), reason="fixture missing")
def test_is_session_expired_false_on_logged_in_home():
    from moneyforward_pk.utils.session_utils import is_session_expired

    resp = _response(LOGGED_IN_HTML, "https://ssnb.x.moneyforward.com/")
    assert is_session_expired(resp) is False
