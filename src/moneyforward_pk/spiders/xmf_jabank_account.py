"""JAバンク (jabank.x.moneyforward.com) 派生 Moneyforward の口座スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.account import MfAccountSpider
from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin


class XmfJabankAccountSpider(XMoneyforwardLoginMixin, MfAccountSpider):
    """``xmf_jabank`` variant 用 account spider.

    URL/parser は ``MfAccountSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_jabank_account"
    variant_name = "xmf_jabank"
