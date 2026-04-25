"""静岡銀行 (shiz.x.moneyforward.com) 派生 Moneyforward の取引明細スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin
from moneyforward_pk.spiders.transaction import MfTransactionSpider


class XmfShizTransactionSpider(XMoneyforwardLoginMixin, MfTransactionSpider):
    """``xmf_shiz`` variant 用 transaction spider.

    URL/parser は ``MfTransactionSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_shiz_transaction"
    variant_name = "xmf_shiz"
