"""linkx家計簿 (linkx.x.moneyforward.com) 派生 Moneyforward の口座スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.account import MfAccountSpider
from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin


class XmfLinkxAccountSpider(XMoneyforwardLoginMixin, MfAccountSpider):
    """``xmf_linkx`` variant 用 account spider.

    URL/parser は ``MfAccountSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_linkx_account"
    variant_name = "xmf_linkx"
