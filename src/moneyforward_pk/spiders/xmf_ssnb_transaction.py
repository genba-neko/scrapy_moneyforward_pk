"""住信SBIネット銀行 派生 Moneyforward の取引明細スパイダー.

T2 で variant 駆動 refactor 後、本ファイルは ``variant_name`` 宣言と
``XMoneyforwardLoginMixin`` の混入のみで成立する.
"""

from __future__ import annotations

from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin
from moneyforward_pk.spiders.transaction import MfTransactionSpider


class XmfSsnbTransactionSpider(XMoneyforwardLoginMixin, MfTransactionSpider):
    """``xmf_ssnb`` variant 用 transaction spider.

    ``MfTransactionSpider`` の URL/parser を継承し,
    ``XMoneyforwardLoginMixin`` で ``x.moneyforward.com`` 系のログインフローを
    上書きする. URL は ``self.variant`` (=``VARIANTS["xmf_ssnb"]``) から解決.
    """

    name = "xmf_ssnb_transaction"
    variant_name = "xmf_ssnb"
