"""Transaction HTML → item parsing."""

from __future__ import annotations

from moneyforward_pk.spiders._parsers import parse_transactions
from tests.helpers import make_response

FIXTURE_HTML = """
<html><body>
<table>
  <tbody class="transaction_list">
    <tr>
      <td class="target-active"></td>
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
