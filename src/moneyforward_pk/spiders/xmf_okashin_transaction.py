"""岡崎信用金庫 (okashin.x.moneyforward.com) 派生 Moneyforward の取引明細スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin
from moneyforward_pk.spiders.transaction import MfTransactionSpider


class XmfOkashinTransactionSpider(XMoneyforwardLoginMixin, MfTransactionSpider):
    """``xmf_okashin`` variant 用 transaction spider.

    URL/parser は ``MfTransactionSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_okashin_transaction"
    variant_name = "xmf_okashin"
