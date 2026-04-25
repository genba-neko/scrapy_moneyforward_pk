"""岡崎信用金庫 (okashin.x.moneyforward.com) 派生 Moneyforward の口座スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.account import MfAccountSpider
from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin


class XmfOkashinAccountSpider(XMoneyforwardLoginMixin, MfAccountSpider):
    """``xmf_okashin`` variant 用 account spider.

    URL/parser は ``MfAccountSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_okashin_account"
    variant_name = "xmf_okashin"
