"""一般 partner portal (x.moneyforward.com) 派生 Moneyforward の取引明細スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin
from moneyforward_pk.spiders.transaction import MfTransactionSpider


class XmfTransactionSpider(XMoneyforwardLoginMixin, MfTransactionSpider):
    """``xmf`` variant 用 transaction spider.

    URL/parser は ``MfTransactionSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_transaction"
    variant_name = "xmf"
