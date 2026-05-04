"""HtmlInspectorMiddleware: opt-in HTML dump for offline debugging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scrapy.http import HtmlResponse, Request

from moneyforward.middlewares.html_inspector import HtmlInspectorMiddleware


def _spider():
    s = MagicMock()
    s.name = "mf_test"
    s.logger = MagicMock()
    return s


def _response(url="https://moneyforward.com/cf", body=b"<html>x</html>"):
    return HtmlResponse(url=url, body=body, request=Request(url=url))


def test_disabled_middleware_does_not_create_files(tmp_path):
    mw = HtmlInspectorMiddleware(output_dir=tmp_path / "inspect", enabled=False)
    resp = _response()
    out = mw.process_response(Request(url=resp.url), resp, _spider())
    assert out is resp
    assert not (tmp_path / "inspect").exists()


def test_disabled_middleware_returns_same_response(tmp_path):
    mw = HtmlInspectorMiddleware(output_dir=tmp_path / "inspect", enabled=False)
    resp = _response()
    assert mw.process_response(Request(url=resp.url), resp, _spider()) is resp


def test_enabled_middleware_dumps_html(tmp_path):
    out_dir = tmp_path / "inspect"
    mw = HtmlInspectorMiddleware(output_dir=out_dir, enabled=True)
    resp = _response(body=b"<html><body>secret-marker</body></html>")
    mw.process_response(Request(url=resp.url), resp, _spider())
    files = list(out_dir.glob("*.html"))
    assert len(files) == 1
    assert b"secret-marker" in files[0].read_bytes()


def test_enabled_middleware_writes_unique_filenames_per_response(tmp_path):
    out_dir = tmp_path / "inspect"
    mw = HtmlInspectorMiddleware(output_dir=out_dir, enabled=True)
    for i in range(3):
        resp = _response(url=f"https://moneyforward.com/p/{i}", body=b"<html>x</html>")
        mw.process_response(Request(url=resp.url), resp, _spider())
    files = list(out_dir.glob("*.html"))
    assert len(files) == 3
    # Filenames must be unique even when rendered within the same second.
    assert len({f.name for f in files}) == 3


def test_enabled_middleware_handles_empty_body(tmp_path):
    out_dir = tmp_path / "inspect"
    mw = HtmlInspectorMiddleware(output_dir=out_dir, enabled=True)
    resp = HtmlResponse(url="https://x/", body=b"", request=Request(url="https://x/"))
    mw.process_response(Request(url=resp.url), resp, _spider())
    # Empty body means no dump.
    assert not list(out_dir.glob("*.html")) or out_dir.exists()


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
