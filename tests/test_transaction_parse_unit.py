"""Transaction HTML → item parsing."""

from __future__ import annotations

from moneyforward_pk.spiders._parsers import parse_transactions
from tests.helpers import make_response

FIXTURE_HTML = """
<html><body>
<table>
  <tbody class="transaction_list">
    <tr class="target-active">
      <td></td>
      <td class="date" data-table-sortable-value="2025/01/15-123456"><span>01/15</span></td>
      <td class="content"><span>スーパー購入</span></td>
      <td class="amount"><span>-1,234</span></td>
      <td class="sub_account_id_hash"><span>財布</span></td>
      <td class="lctg"><a>食費</a></td>
      <td class="mctg"><a>食料品</a></td>
      <td class="memo"><span></span></td>
    </tr>
    <tr>
      <td class="date" data-table-sortable-value="2025/01/16-789"><span>01/16</span></td>
      <td class="content"><span>給与振込</span></td>
      <td class="amount"><span>250,000</span></td>
      <td class="note calc" data-original-title="詳細">給与口座</td>
      <td class="lctg"><a>収入</a></td>
      <td class="mctg"><a>給与</a></td>
      <td class="memo"><span></span></td>
    </tr>
  </tbody>
</table>
</body></html>
"""


# Pin: nested .target-active on a child cell must NOT promote is_active=True.
# Only the <tr>'s own class list governs is_active.
NESTED_ACTIVE_FIXTURE_HTML = """
<html><body>
<table>
  <tbody class="transaction_list">
    <tr>
      <td><i class="target-active icon"></i></td>
      <td class="date" data-table-sortable-value="2025/01/15-111"><span>01/15</span></td>
      <td class="content"><span>nested</span></td>
      <td class="amount"><span>-1</span></td>
      <td class="sub_account_id_hash"><span>cash</span></td>
      <td class="lctg"><a>etc</a></td>
      <td class="mctg"><a>etc</a></td>
      <td class="memo"><span></span></td>
    </tr>
  </tbody>
</table>
</body></html>
"""


TRANSFER_FIXTURE_HTML = """
<html><body>
<table>
  <tbody class="transaction_list">
    <tr>
      <td class="date" data-table-sortable-value="2025/01/17-555"><span>01/17</span></td>
      <td class="content"><span>口座間振替</span></td>
      <td class="amount"><span>-50,000</span></td>
      <td class="calc" data-original-title="振替詳細">
        <div class="transfer_account_box">→</div>
        <div class="transfer_account_box_02"><a>みずほ普通</a></div>
      </td>
      <td class="lctg"><a>振替</a></td>
      <td class="mctg"><a></a></td>
      <td class="memo"><span></span></td>
    </tr>
  </tbody>
</table>
</body></html>
"""


def test_parse_transactions_manual_and_auto():
    response = make_response(FIXTURE_HTML)
    items = list(parse_transactions(response, 2025, 1))
    assert len(items) == 2

    manual = items[0]
    assert manual["year_month"] == "202501"
    assert manual["data_table_sortable_value"] == "2025/01/15-123456"
    assert manual["year"] == 2025
    assert manual["month"] == 1
    assert manual["day"] == 15
    assert manual["amount_number"] == -1234
    assert manual["transaction_account"] == "財布"
    assert manual["lctg"] == "食費"
    assert manual["is_active"] is True

    auto = items[1]
    assert auto["amount_number"] == 250000
    assert auto["transaction_account"] == "給与口座"
    assert auto["transaction_detail"] == "詳細"
    assert auto["is_active"] is False


def test_parse_transactions_skips_rows_without_date():
    response = make_response(
        '<table><tr class="transaction_list"><tr><td>x</td></tr></tr></table>'
    )
    assert list(parse_transactions(response, 2025, 1)) == []


def test_parse_transactions_extracts_transfer_branch():
    """_extract_account_cells: td.calc with non-empty data-original-title."""
    response = make_response(TRANSFER_FIXTURE_HTML)
    items = list(parse_transactions(response, 2025, 1))
    assert len(items) == 1
    transfer = items[0]
    assert transfer["amount_number"] == -50_000
    assert transfer["transaction_account"] == "みずほ普通"
    assert transfer["transaction_detail"] == "振替詳細"


def test_parse_transactions_is_active_only_when_on_row_class():
    """iter2 T2: nested .target-active in child cells must not flip is_active."""
    response = make_response(NESTED_ACTIVE_FIXTURE_HTML)
    items = list(parse_transactions(response, 2025, 1))
    assert len(items) == 1
    assert items[0]["is_active"] is False


def test_parse_transactions_date_sort_re_requires_four_digit_year():
    """iter2 T2: a sort value with a 2-digit year must be rejected as malformed."""
    body = (
        "<table><tr class='transaction_list'>"
        "<td class='date' data-table-sortable-value='25/01/15-1'>x</td>"
        "</tr></table>"
    )
    response = make_response(body)
    assert list(parse_transactions(response, 2025, 1)) == []
