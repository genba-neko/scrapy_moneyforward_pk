"""Account HTML → item parsing + update-detection."""

from __future__ import annotations

import hashlib
from datetime import date

from moneyforward_pk.spiders._parsers import parse_accounts
from tests.helpers import make_response

FIXTURE_HTML = """
<html><body>
<table>
  <tr><th>金融機関</th><th>残高</th><th>更新日</th><th>ステータス</th></tr>
  <tr>
    <td>みずほ銀行(本サイト)追記</td>
    <td>12,345円</td>
    <td>2025/01/15 12:00</td>
    <td>
      <span id="js-hidden-status-sentence-span-1">隠し</span>
      <span id="js-status-sentence-span-1">正常</span>
    </td>
  </tr>
  <tr>
    <td>三井住友銀行</td>
    <td>500,000円</td>
    <td>2025/01/15 11:30</td>
    <td>
      <span id="js-status-sentence-span-2">更新中</span>
    </td>
  </tr>
</table>
</body></html>
"""


def test_parse_accounts_basic():
    response = make_response(FIXTURE_HTML)
    items, is_updating = parse_accounts(response, today=date(2025, 1, 15))

    assert is_updating is True
    assert len(items) == 2

    mizuho = items[0]
    assert mizuho["account_name"] == "みずほ銀行"
    expected_key = hashlib.sha256(
        "みずほ銀行(本サイト)追記".encode("utf-8")
    ).hexdigest()
    assert mizuho["account_item_key"] == expected_key
    assert mizuho["account_status"] == "正常"
    assert mizuho["year_month_day"] == "20250115"

    smbc = items[1]
    assert smbc["account_name"] == "三井住友銀行"
    assert smbc["account_status"] == "更新中"


def test_parse_accounts_all_done():
    html = FIXTURE_HTML.replace("更新中", "正常")
    response = make_response(html)
    _, is_updating = parse_accounts(response, today=date(2025, 1, 15))
    assert is_updating is False


_UPDATING_ONLY_HTML = """
<html><body>
<table>
  <tr><th>金融機関</th><th>残高</th><th>更新日</th><th>ステータス</th></tr>
  <tr>
    <td>更新中銀行</td>
    <td>1,000円</td>
    <td>2025/01/15 12:00</td>
    <td><span id="js-status-sentence-span-1">更新中</span></td>
  </tr>
</table>
</body></html>
"""


def test_parse_accounts_is_updating_branch():
    """iter2 T4: a single 更新中 row must flip is_updating True for the caller."""
    response = make_response(_UPDATING_ONLY_HTML)
    items, is_updating = parse_accounts(response, today=date(2025, 1, 15))
    assert is_updating is True
    assert len(items) == 1
    assert items[0]["account_status"] == "更新中"
