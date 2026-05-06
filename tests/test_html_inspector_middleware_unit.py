"""HtmlInspectorMiddleware: opt-in HTML dump for offline debugging."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest
from scrapy.http import HtmlResponse, Request

from moneyforward.middlewares.html_inspector import (
    HtmlInspectorMiddleware,
    _extract_sub_path,
)


def _spider(name: str = "mf_test"):
    s = MagicMock()
    s.name = name
    s.logger = MagicMock()
    return s


def _response(url="https://moneyforward.com/cf", body=b"<html>x</html>", status=200):
    return HtmlResponse(url=url, body=body, status=status, request=Request(url=url))


def _enabled_mw(tmp_path: Path) -> tuple[HtmlInspectorMiddleware, MagicMock]:
    mw = HtmlInspectorMiddleware(output_dir=tmp_path / "inspect", enabled=True)
    spider = _spider()
    mw.spider_opened(spider)
    return mw, spider


# ------------------------------------------------------------------
# _extract_sub_path
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://moneyforward.com/accounts/show", "accounts/show"),
        ("https://moneyforward.com/cf", "cf"),
        ("https://moneyforward.com/", "index"),
        ("https://moneyforward.com", "index"),
        ("https://moneyforward.com/a/b/c", "a/b/c"),
    ],
)
def test_extract_sub_path(url, expected):
    assert _extract_sub_path(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://moneyforward.com/../../etc/passwd",
        "https://moneyforward.com/../secret",
        "https://moneyforward.com/accounts/../../etc/shadow",
    ],
)
def test_extract_sub_path_rejects_traversal(url):
    result = _extract_sub_path(url)
    assert (
        ".." not in result
    )  # traversal segments stripped; remaining path stays in run_dir


# ------------------------------------------------------------------
# Disabled middleware
# ------------------------------------------------------------------


def test_disabled_middleware_does_not_create_files(tmp_path):
    mw = HtmlInspectorMiddleware(output_dir=tmp_path / "inspect", enabled=False)
    resp = _response()
    out = mw.process_response(Request(url=resp.url), resp)
    assert out is resp
    assert not (tmp_path / "inspect").exists()


def test_disabled_middleware_returns_same_response(tmp_path):
    mw = HtmlInspectorMiddleware(output_dir=tmp_path / "inspect", enabled=False)
    resp = _response()
    assert mw.process_response(Request(url=resp.url), resp) is resp


# ------------------------------------------------------------------
# spider_opened / spider_closed
# ------------------------------------------------------------------


def test_spider_opened_creates_run_dir_and_flow_log(tmp_path):
    mw = HtmlInspectorMiddleware(output_dir=tmp_path / "inspect", enabled=True)
    spider = _spider("transaction")
    mw.spider_opened(spider)
    assert mw.run_dir.exists()
    assert mw.run_dir.name.endswith("_transaction")
    flow_log = mw.run_dir / "flow.log"
    assert flow_log.exists()
    meta = json.loads(flow_log.read_text(encoding="utf-8").splitlines()[0])
    assert meta["type"] == "meta"
    assert meta["spider"] == "transaction"


def test_spider_opened_resets_seq(tmp_path):
    mw = HtmlInspectorMiddleware(output_dir=tmp_path / "inspect", enabled=True)
    spider = _spider()
    mw.spider_opened(spider)
    resp = _response()
    mw.process_response(Request(url=resp.url), resp)
    assert mw._seq == 1
    mw.spider_opened(spider)
    assert mw._seq == 0


def test_spider_closed_closes_flow_log(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    assert mw._flow_fh is not None
    mw.spider_closed(spider)
    assert mw._flow_fh is None


def test_process_response_before_spider_opened_is_noop(tmp_path):
    mw = HtmlInspectorMiddleware(output_dir=tmp_path / "inspect", enabled=True)
    resp = _response()
    result = mw.process_response(Request(url=resp.url), resp)
    assert result is resp
    assert (
        not list((tmp_path / "inspect").rglob("*.html"))
        if (tmp_path / "inspect").exists()
        else True
    )


# ------------------------------------------------------------------
# Dump content and structure
# ------------------------------------------------------------------


def test_enabled_middleware_dumps_html(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    resp = _response(body=b"<html><body>secret-marker</body></html>")
    mw.process_response(Request(url=resp.url), resp)
    files = list(mw.run_dir.rglob("*.html"))
    assert len(files) == 1
    assert "secret-marker" in files[0].read_text(encoding="utf-8")


def test_url_path_maps_to_subdirectory(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    resp = _response(url="https://moneyforward.com/accounts/show")
    mw.process_response(Request(url=resp.url), resp)
    expected_dir = mw.run_dir / "accounts"
    assert expected_dir.exists()
    assert len(list(expected_dir.glob("*.html"))) == 1


def test_error_status_gets_error_suffix(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    resp = _response(url="https://moneyforward.com/accounts/show", status=404)
    mw.process_response(Request(url=resp.url), resp)
    files = list(mw.run_dir.rglob("*_error.html"))
    assert len(files) == 1


def test_ok_status_has_no_error_suffix(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    resp = _response(url="https://moneyforward.com/accounts/show", status=200)
    mw.process_response(Request(url=resp.url), resp)
    files = list(mw.run_dir.rglob("*_error.html"))
    assert len(files) == 0


def test_enabled_middleware_writes_unique_filenames_per_response(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    for i in range(3):
        resp = _response(url=f"https://moneyforward.com/p/{i}", body=b"<html>x</html>")
        mw.process_response(Request(url=resp.url), resp)
    files = list(mw.run_dir.rglob("*.html"))
    assert len(files) == 3
    assert len({f.name for f in files}) == 3


def test_same_url_twice_writes_two_files(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    for _ in range(2):
        resp = _response(url="https://moneyforward.com/accounts/show")
        mw.process_response(Request(url=resp.url), resp)
    files = list(mw.run_dir.rglob("*.html"))
    assert len(files) == 2


def test_enabled_middleware_handles_empty_body(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    resp = HtmlResponse(url="https://x/", body=b"", request=Request(url="https://x/"))
    mw.process_response(Request(url=resp.url), resp)
    assert not list(mw.run_dir.rglob("*.html"))


# ------------------------------------------------------------------
# flow.log
# ------------------------------------------------------------------


def test_flow_log_contains_entries(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    resp = _response(url="https://moneyforward.com/accounts/show")
    mw.process_response(Request(url=resp.url), resp)
    lines = (mw.run_dir / "flow.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # meta + 1 entry
    entry = json.loads(lines[1])
    assert entry["seq"] == 1
    assert entry["path"] == "accounts/show"
    assert entry["error"] is False


def test_flow_log_error_entry(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    resp = _response(url="https://moneyforward.com/accounts/show", status=500)
    mw.process_response(Request(url=resp.url), resp)
    lines = (mw.run_dir / "flow.log").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    assert entry["error"] is True


def test_flow_log_file_field_uses_forward_slash(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    resp = _response(url="https://moneyforward.com/accounts/show")
    mw.process_response(Request(url=resp.url), resp)
    lines = (mw.run_dir / "flow.log").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    assert "\\" not in entry["file"]


# ------------------------------------------------------------------
# Playwright listener
# ------------------------------------------------------------------


def test_playwright_listener_registered_once_per_page(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    page = MagicMock()
    for _ in range(3):
        req = Request(url="https://moneyforward.com/cf", meta={"playwright_page": page})
        resp = _response()
        mw.process_response(req, resp)
    assert page.on.call_count == 1
    assert page.on.call_args == call("load", page.on.call_args[0][1])


def test_playwright_listener_different_pages_each_registered(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    pages = [MagicMock() for _ in range(3)]
    for page in pages:
        req = Request(url="https://moneyforward.com/cf", meta={"playwright_page": page})
        resp = _response()
        mw.process_response(req, resp)
    for page in pages:
        assert page.on.call_count == 1


def test_playwright_listener_callback_label(tmp_path):
    mw, spider = _enabled_mw(tmp_path)
    page = MagicMock()
    req = Request(url="https://moneyforward.com/cf", meta={"playwright_page": page})
    req.callback = MagicMock(__name__="parse_accounts")
    resp = _response()
    mw.process_response(req, resp)
    assert page.on.called
    assert page.on.call_args[0][0] == "load"


# ------------------------------------------------------------------
# from_crawler
# ------------------------------------------------------------------


def test_from_crawler_disabled_by_default(tmp_path):
    crawler = MagicMock()
    crawler.settings.get = lambda key, default=None: {
        "MONEYFORWARD_HTML_INSPECTOR": False,
        "MONEYFORWARD_RUNTIME_DIR": str(tmp_path),
        "MONEYFORWARD_HTML_INSPECTOR_DIR": "",
    }.get(key, default)
    mw = HtmlInspectorMiddleware.from_crawler(crawler)
    assert mw.enabled is False


@pytest.mark.parametrize("flag", ["true", "1", "yes", "on", "TRUE"])
def test_from_crawler_enabled_via_truthy_flag(tmp_path, flag):
    crawler = MagicMock()
    crawler.settings.get = lambda key, default=None: {
        "MONEYFORWARD_HTML_INSPECTOR": flag,
        "MONEYFORWARD_RUNTIME_DIR": str(tmp_path),
        "MONEYFORWARD_HTML_INSPECTOR_DIR": "",
    }.get(key, default)
    mw = HtmlInspectorMiddleware.from_crawler(crawler)
    assert mw.enabled is True


def test_from_crawler_custom_dir_relative(tmp_path):
    crawler = MagicMock()
    crawler.settings.get = lambda key, default=None: {
        "MONEYFORWARD_HTML_INSPECTOR": True,
        "MONEYFORWARD_RUNTIME_DIR": str(tmp_path),
        "MONEYFORWARD_HTML_INSPECTOR_DIR": "custom/sub",
    }.get(key, default)
    mw = HtmlInspectorMiddleware.from_crawler(crawler)
    assert mw.output_dir == Path(tmp_path) / "custom" / "sub"


def test_from_crawler_custom_dir_absolute(tmp_path):
    abs_dir = str(tmp_path / "abs_inspect")
    crawler = MagicMock()
    crawler.settings.get = lambda key, default=None: {
        "MONEYFORWARD_HTML_INSPECTOR": True,
        "MONEYFORWARD_RUNTIME_DIR": str(tmp_path),
        "MONEYFORWARD_HTML_INSPECTOR_DIR": abs_dir,
    }.get(key, default)
    mw = HtmlInspectorMiddleware.from_crawler(crawler)
    assert mw.output_dir == Path(abs_dir)


def test_from_crawler_connects_signals_when_enabled(tmp_path):
    crawler = MagicMock()
    crawler.settings.get = lambda key, default=None: {
        "MONEYFORWARD_HTML_INSPECTOR": True,
        "MONEYFORWARD_RUNTIME_DIR": str(tmp_path),
        "MONEYFORWARD_HTML_INSPECTOR_DIR": "",
    }.get(key, default)
    HtmlInspectorMiddleware.from_crawler(crawler)
    assert crawler.signals.connect.called


def test_from_crawler_no_signals_when_disabled(tmp_path):
    crawler = MagicMock()
    crawler.settings.get = lambda key, default=None: {
        "MONEYFORWARD_HTML_INSPECTOR": False,
        "MONEYFORWARD_RUNTIME_DIR": str(tmp_path),
        "MONEYFORWARD_HTML_INSPECTOR_DIR": "",
    }.get(key, default)
    HtmlInspectorMiddleware.from_crawler(crawler)
    assert not crawler.signals.connect.called
