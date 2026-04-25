"""xmf_ssnb (住信SBIネット銀行) 派生スパイダーのパーサ互換性テスト.

xmf_ssnb は MfTransactionSpider / MfAccountSpider / MfAssetAllocationSpider と
同じ HTML 構造をベースに `_parsers.py` を共有する設計のため、ここでは
変換結果が mf 系と同じ Item 形になることを pin 留めする.
"""

from __future__ import annotations

from datetime import date

from scrapy.http import HtmlResponse, Request

from moneyforward_pk.spiders._parsers import parse_transactions
from moneyforward_pk.spiders.xmf_ssnb_account import XmfSsnbAccountSpider
from moneyforward_pk.spiders.xmf_ssnb_asset_allocation import (
    XmfSsnbAssetAllocationSpider,
)
from moneyforward_pk.spiders.xmf_ssnb_transaction import XmfSsnbTransactionSpider


def _response(
    body: str, url: str = "https://ssnb.x.moneyforward.com/cf"
) -> HtmlResponse:
    return HtmlResponse(
        url=url,
        body=body.encode("utf-8"),
        encoding="utf-8",
        request=Request(url=url),
    )


def test_xmf_ssnb_transaction_fixture_parses(fixture_html):
    """匿名化済 SSNB fixture を mf と同じ parser に通して 3 行抽出を確認."""
    body = fixture_html("xmf_ssnb_transaction_legacy.html")
    items = list(parse_transactions(_response(body), 2020, 1))
    assert len(items) == 3
    # 1 行目: 振替セル (transfer_account_box あり)
    first = items[0]
    assert first["year_month"] == "202001"
    assert first["data_table_sortable_value"].startswith("2020/01/27")
    assert first["amount_number"] == 20000
    assert first["transaction_account"] == "住信SBI銀行"
    assert first["transaction_transfer"] == "楽天銀行"
    # 2 行目: 自動入力 (note.calc) + 負値
    second = items[1]
    assert second["amount_number"] == -9640
    assert second["transaction_account"] == "楽天銀行"
    assert second["lctg"] == "お金・カード"
    # 3 行目: 給与収入
    third = items[2]
    assert third["amount_number"] == 300000
    assert third["lctg"] == "収入"


def test_xmf_ssnb_transaction_spider_attributes():
    spider = XmfSsnbTransactionSpider()
    assert spider.name == "xmf_ssnb_transaction"
    assert spider.variant.name == "xmf_ssnb"
    assert spider.variant.transactions_url == "https://ssnb.x.moneyforward.com/cf"
    assert spider.is_partner_portal is True


def test_xmf_ssnb_asset_allocation_spider_attributes():
    spider = XmfSsnbAssetAllocationSpider()
    assert spider.name == "xmf_ssnb_asset_allocation"
    assert spider.variant.name == "xmf_ssnb"
    assert (
        spider.variant.asset_allocation_url
        == "https://ssnb.x.moneyforward.com/bs/portfolio"
    )
    assert spider.is_partner_portal is True


def test_xmf_ssnb_account_spider_attributes():
    spider = XmfSsnbAccountSpider()
    assert spider.name == "xmf_ssnb_account"
    assert spider.variant.name == "xmf_ssnb"
    assert spider.variant.accounts_url == "https://ssnb.x.moneyforward.com/accounts"
    assert spider.is_partner_portal is True


def test_xmf_ssnb_spiders_inherit_partner_login_mixin():
    """3 spider すべてが XMoneyforwardLoginMixin を継承して partner login を使う.

    Notes
    -----
    test_spiders_base_unit.py が ``importlib.reload`` でモジュールを再読込する
    ため、別ロード ID の ``XMoneyforwardLoginMixin`` を import すると
    ``issubclass`` が False を返す. spider クラスの MRO 上に実際に
    ``XMoneyforwardLoginMixin`` 名のクラスがあるかをチェックする形にする.
    """
    for cls in (
        XmfSsnbTransactionSpider,
        XmfSsnbAssetAllocationSpider,
        XmfSsnbAccountSpider,
    ):
        mro_names = {c.__name__ for c in cls.__mro__}
        assert "XMoneyforwardLoginMixin" in mro_names, f"{cls} MRO: {mro_names}"


def test_xmf_ssnb_account_request_url():
    spider = XmfSsnbAccountSpider()
    req = spider._accounts_request(is_update=False, attempt=0)
    assert req.url == "https://ssnb.x.moneyforward.com/accounts"
    assert spider.allowed_domains == ["ssnb.x.moneyforward.com"]
    # date 引数は parse 経路でしか使わないので spider 単体では検証不要だが、
    # variant の今日付 fixture 化に備え import を維持.
    _ = date.today()
