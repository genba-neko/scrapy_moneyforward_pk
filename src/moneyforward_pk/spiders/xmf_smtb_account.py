"""三井住友信託銀行 (smtb.x.moneyforward.com) 派生 Moneyforward の口座スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.account import MfAccountSpider
from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin


class XmfSmtbAccountSpider(XMoneyforwardLoginMixin, MfAccountSpider):
    """``xmf_smtb`` variant 用 account spider.

    URL/parser は ``MfAccountSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_smtb_account"
    variant_name = "xmf_smtb"
