"""Account HTML → item parsing + update-detection."""

from __future__ import annotations

import hashlib
from datetime import date

from moneyforward.spiders._parsers import parse_accounts
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


# Realistic shape of the live MoneyForward /accounts table where the bank name
# is wrapped in nested <a>/<span> elements with newlines between them. Without
# the legacy join_strip equivalent, ``raw_name`` would carry literal ``\n`` and
# the downstream sha256 input would diverge from legacy DynamoDB SK values.
_NESTED_NEWLINE_HTML = """
<html><body>
<table>
  <tr><th>金融機関</th><th>残高</th><th>更新日</th><th>ステータス</th></tr>
  <tr>
    <td>
      <a href="https://moneyforward.com/accounts/show/abc">住信SBIネット銀行</a>
      <span>
(

本サイト
)

203*******</span>
    </td>
    <td>
      <span>
55,189円
</span>
    </td>
    <td>
2022/12/27

(05/03 17:35)
    </td>
    <td>
      <span id="js-status-sentence-span-1">正常</span>
    </td>
  </tr>
</table>
</body></html>
"""


def test_parse_accounts_join_strip_compat_with_legacy():
    """Issue #42 compat: raw_name SHA256 input must follow legacy join_strip rule.

    Legacy ``MfSpider.join_strip`` (mf_transaction.py:271) removes ``\\n``,
    ``\\t``, ``,`` then strips. Without the same normalization, real MF HTML
    that embeds newlines between nested tags would leak ``\\n`` into raw_name
    and the SHA256 input would diverge from what legacy produced for the
    same account.

    Note: bit-perfect SK equality with the legacy DynamoDB dump cannot be
    asserted here because the live MF HTML structure may differ from the
    legacy capture (additional form/button text inside the same ``<td>``
    contributes to ``*::text``). We test the join_strip invariants instead:
    no ``\\n``/``\\t``/``,`` should remain in fields that go through this
    normalization, and the sha256 digest must be a 64-char hex string of the
    legacy form.
    """
    response = make_response(_NESTED_NEWLINE_HTML)
    items, _ = parse_accounts(response, today=date(2025, 1, 15))
    assert len(items) == 1
    item = items[0]

    # account_item_key must be a 64-char lowercase hex (sha256 of join_strip
    # output). Same shape as legacy DynamoDB SK values.
    key = item["account_item_key"]
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)

    # Downstream fields must not leak \n / \t / , (legacy join_strip rule).
    assert "\n" not in item["account_amount_number"]
    assert "\t" not in item["account_amount_number"]
    assert "," not in item["account_amount_number"]
    assert "\n" not in item["account_date"]
    assert "\t" not in item["account_date"]
    # account_name (display) is the trimmed prefix when ``(本サイト)`` matches
    # the join_strip-normalized raw_name (so newlines around ``(本サイト)``
    # no longer block the trim regex).
    assert item["account_name"] == "住信SBIネット銀行"


def test_join_strip_helper_matches_legacy_rules():
    """`_parsers._join_strip` の入出力を pin する単体 test (Opus レビュー対応)。

    Legacy ``MfSpider.join_strip`` (mf_transaction.py:271) は list 入力前提の
    ``"".join(texts).replace('\\n','').replace('\\t','').replace(',','').strip()``。
    新実装はそれに加え None / str を gentle に受ける super-set 動作。両者の
    rule-level equivalence と新実装の防御挙動を pin する。
    """
    from moneyforward.spiders._parsers import _join_strip

    # legacy 等価ケース: list[str] 入力で \n / \t / , 除去 + strip
    assert _join_strip(["  住信SBI\n銀行\t", ",支店\n"]) == "住信SBI銀行支店"
    assert _join_strip(["12,345円"]) == "12345円"
    assert _join_strip(["\n\n\t  ", "正常"]) == "正常"
    assert _join_strip([""]) == ""

    # super-set 拡張 (新実装の防御): None / str を受ける
    assert _join_strip(None) == ""
    assert _join_strip("単一文字列\n,") == "単一文字列"

    # 残す挙動: \r や半角スペースは除去しない (legacy 同じ)
    assert _join_strip(["A\rB"]) == "A\rB"
    assert _join_strip(["A B C"]) == "A B C"


_NESTED_STATUS_HTML = """
<html><body>
<table>
  <tr><th>金融機関</th><th>残高</th><th>更新日</th><th>ステータス</th></tr>
  <tr>
    <td>みずほ銀行</td>
    <td>12345円</td>
    <td>2025/01/15 12:00</td>
    <td>
      <span id="js-hidden-status-sentence-span-X" style="display:none">隠し</span>
      <span id="js-status-sentence-span-X"><span>正常</span></span>
    </td>
  </tr>
  <tr>
    <td>みなと銀行</td>
    <td>1000円</td>
    <td>2025/01/15 12:00</td>
    <td>
      <span id="some-other-id">別物</span>
    </td>
  </tr>
</table>
</body></html>
"""


def test_parse_accounts_status_nested_span_legacy_compat():
    """Issue #42 compat: 入れ子 span 構造 + ``---`` fallback の挙動を pin する。

    旧 PJ ``mf_account.py:168-174`` の挙動:
    - matching span (``js-status-sentence-span-`` 含む id) の入れ子 span の
      text を取得 (``status_span.css('span::text').get()``)
    - matching span がそもそも存在しない場合は loop 前初期化の ``"---"``
      が残る (空 text で上書きされた場合は ``""`` になる、これも legacy 通り)

    実 MF HTML が ``<span id="..."><span>正常</span></span>`` の入れ子構造を
    取るケースと、status span が無い (または別 id の) ケースの両方で、
    legacy 同等出力になることを検証する。
    """
    response = make_response(_NESTED_STATUS_HTML)
    items, _ = parse_accounts(response, today=date(2025, 1, 15))
    assert len(items) == 2
    # 入れ子 span 構造から「正常」が取れる
    assert items[0]["account_status"] == "正常"
    # matching span (js-status-sentence-span-) が存在しない → "---" fallback
    assert items[1]["account_status"] == "---"


def test_parse_accounts_legacy_six_fields_only():
    """Issue #42 compat: MoneyforwardAccountItem は legacy 6 フィールドのまま。

    旧 PJ ``scrapy_moneyforward/src/moneyforward/items.py:46-54`` と同じ
    フィールド集合であることを pin。新規 attribute (login_user 等) を追加
    する変更が入った場合に regression として落ちる。
    """
    from moneyforward.items import MoneyforwardAccountItem

    expected = {
        "year_month_day",
        "account_item_key",
        "account_name",
        "account_amount_number",
        "account_date",
        "account_status",
    }
    assert set(MoneyforwardAccountItem.fields.keys()) == expected
