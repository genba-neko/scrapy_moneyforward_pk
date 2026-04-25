"""SSNB (静岡新聞 SBS) 派生 Moneyforward の取引明細スパイダー雛形.

c3 iter1 では variant registry を参照する skeleton のみ提供する.
URL/selector の本格実装は c3 iter2 以降で実環境調査済み次第対応する.
"""

from __future__ import annotations

from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin
from moneyforward_pk.spiders.transaction import MfTransactionSpider
from moneyforward_pk.spiders.variants import get_variant


class XmfSsnbTransactionSpider(XMoneyforwardLoginMixin, MfTransactionSpider):
    """``xmf_ssnb`` variant 用 transaction spider 雛形.

    ``MfTransactionSpider`` を継承し、``XMoneyforwardLoginMixin`` で
    ``x.moneyforward.com`` 系のログインフローを上書きする. variant の
    URL は ``self.variant`` から取得する想定 (本格実装時に
    ``MfTransactionSpider.parse_month`` を override する).

    Notes
    -----
    現状は ``scrapy list`` で 4 件目として認識されることのみを保証する
    skeleton. クロール本実装は c3 iter2 以降で行う.
    """

    name = "xmf_ssnb_transaction"
    variant_name = "xmf_ssnb"
    allowed_domains = ["ssnb.x.moneyforward.com"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.variant = get_variant(self.variant_name)
        # variant に従って起点 URL を切り替え (本格実装で URL 全体を移行する)
        self.start_url = self.variant.base_url
        self.is_partner_portal = self.variant.is_partner_portal
