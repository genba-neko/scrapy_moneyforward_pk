"""Asset allocation HTML → item parsing."""

from __future__ import annotations

from datetime import date

from moneyforward_pk.spiders._parsers import parse_asset_allocation
from tests.helpers import make_response

FIXTURE_HTML = """
<html><body>
<table>
  <tr>
    <th><a href="/bs/portfolio#portfolio_det_depo">預金・現金・仮想通貨</a></th>
    <td>246,151円</td>
  </tr>
  <tr>
    <th><a href="/bs/portfolio#portfolio_det_mf">投資信託</a></th>
    <td>1,000,000円</td>
  </tr>
</table>
</body></html>
"""


# Two tables: the legacy parser must restrict itself to the first one, so
# rows in the trailing summary table must NOT leak into the iterator.
SECOND_TABLE_FIXTURE = """
<html><body>
<table>
  <tr>
    <th><a href="/bs/portfolio#portfolio_det_depo">預金・現金・仮想通貨</a></th>
    <td>246,151円</td>
  </tr>
</table>
<table>
  <tr>
    <th><a href="/bs/portfolio#portfolio_det_unwanted">合計サマリ</a></th>
    <td>1,000,000円</td>
  </tr>
</table>
</body></html>
"""


def test_parse_asset_allocation_basic():
    response = make_response(FIXTURE_HTML)
    fixed = date(2025, 1, 15)
    items = list(
        parse_asset_allocation(
            response, "mf_asset_allocation", "user@example.com", today=fixed
        )
    )
    assert len(items) == 2

    first = items[0]
    assert first["year_month_day"] == "20250115"
    assert first["asset_name"] == "預金・現金・仮想通貨"
    assert first["asset_type"] == "portfolio_det_depo"
    assert first["amount_value"] == 246151
    assert (
        first["asset_item_key"]
        == "mf_asset_allocation-user@example.com-portfolio_det_depo"
    )
    assert first["date"] == "2025/01/15"

    second = items[1]
    assert second["asset_type"] == "portfolio_det_mf"
    assert second["amount_value"] == 1_000_000


def test_parse_asset_allocation_empty():
    response = make_response("<html><body></body></html>")
    items = list(
        parse_asset_allocation(
            response, "mf_asset_allocation", "u", today=date(2025, 1, 1)
        )
    )
    assert items == []


def test_parse_asset_allocation_includes_all_tables_today():
    """Document current behaviour: the parser walks every <table> on the page.

    The legacy spec required only the first table. Tracked for an iter2
    parser fix; this test pins the present (regressed) behaviour so the
    intentional fix in iter2 produces a visible diff.
    """
    response = make_response(SECOND_TABLE_FIXTURE)
    items = list(
        parse_asset_allocation(
            response, "mf_asset_allocation", "u", today=date(2025, 1, 1)
        )
    )
    asset_types = [it["asset_type"] for it in items]
    assert "portfolio_det_depo" in asset_types
    # Current parser leaks the second table; iter2 fix flips this to NOT in.
    assert "portfolio_det_unwanted" in asset_types
