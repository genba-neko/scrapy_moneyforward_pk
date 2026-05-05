"""Real-HTML fixture regression tests against the legacy MoneyForward markup.

The fixtures under ``tests/fixtures/*_legacy.html`` are minimised slices of
real captures from the legacy ``scrapy_moneyforward`` project (PII scrubbed,
banner/script-heavy DOM removed). They exercise selectors against authentic
markup so iterations cannot silently regress on real-world HTML shape.
"""

from __future__ import annotations

from datetime import date

from scrapy.http import HtmlResponse, Request

from moneyforward.spiders._parsers import (
    parse_accounts,
    parse_asset_allocation,
    parse_transactions,
)


def _response(body: str, url: str = "https://moneyforward.com/") -> HtmlResponse:
    return HtmlResponse(
        url=url,
        body=body.encode("utf-8"),
        encoding="utf-8",
        request=Request(url=url),
    )


def test_parse_asset_allocation_real_legacy(fixture_html):
    """Legacy /bs/portfolio capture yields the first-table assets only."""
    body = fixture_html("mf_asset_allocation_legacy.html")
    items = list(
        parse_asset_allocation(
            _response(body),
            "mf_asset_allocation",
            "user@example.com",
            today=date(2025, 1, 15),
        )
    )
    asset_types = [it["asset_type"] for it in items]
    # The fixture's first table holds two asset rows; everything else (footer
    # tables, pop-overs) must NOT leak into the iterator.
    assert asset_types == ["portfolio_det_depo", "portfolio_det_po"]
    assert items[0]["amount_value"] == 0
    assert items[1]["amount_value"] == 1705
    assert items[1]["asset_item_key"].endswith("portfolio_det_po")


def test_parse_accounts_real_legacy(fixture_html):
    """Legacy /accounts capture yields a non-empty account list."""
    body = fixture_html("mf_accounts_legacy.html")
    items, is_updating = parse_accounts(_response(body), today=date(2025, 1, 15))
    # The captured fixture shows 9 registered services with a stable header.
    assert len(items) == 9
    # No row carries the "更新中" status in the captured snapshot.
    assert is_updating is False
    # Every row must have a stable account_item_key derived from the raw name.
    keys = {it["account_item_key"] for it in items}
    assert len(keys) == 9


def test_parse_transactions_real_legacy(fixture_html):
    """Legacy /cf capture yields rows whose class is on the ``<tr>`` itself.

    iter2 T1: ``parse_transactions`` accepts both ``tr.transaction_list`` and
    ``.transaction_list tr`` shapes. The captured fixture exposes three rows
    with the class on ``<tr>`` directly.
    """
    body = fixture_html("mf_transaction_legacy.html")
    items = list(parse_transactions(_response(body)))
    assert len(items) == 3
    first = items[0]
    assert first["year_month"] == "201911"
    assert first["data_table_sortable_value"].startswith("2019/11/30")
    assert first["amount_number"] == -1458
    # is_active must be True because the legacy fixture flags target-active.
    assert first["is_active"] is True
    assert first["lctg"] == "食費"
