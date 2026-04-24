"""Session detection helpers."""

from __future__ import annotations

from moneyforward_pk.utils.session_utils import is_login_url, is_session_expired
from tests.helpers import make_response


def test_is_login_url_matches_sign_in():
    assert is_login_url("https://moneyforward.com/sign_in")
    assert is_login_url("https://moneyforward.com/sign_in?x=1")
    assert is_login_url("https://smtb.x.moneyforward.com/users/sign_in")


def test_is_login_url_rejects_normal_urls():
    assert not is_login_url("https://moneyforward.com/cf")
    assert not is_login_url("https://moneyforward.com/bs/portfolio")


def test_is_session_expired_from_title():
    resp = make_response(
        "<html><head><title>ログイン - マネーフォワード</title></head></html>",
        url="https://moneyforward.com/cf",
    )
    assert is_session_expired(resp)


def test_is_session_expired_false_for_normal_page():
    resp = make_response(
        "<html><head><title>家計簿</title></head></html>",
        url="https://moneyforward.com/cf",
    )
    assert not is_session_expired(resp)
