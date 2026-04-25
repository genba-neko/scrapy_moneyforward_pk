"""三井住友信託銀行 (smtb.x.moneyforward.com) 派生 Moneyforward の資産配分スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.asset_allocation import MfAssetAllocationSpider
from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin


class XmfSmtbAssetAllocationSpider(XMoneyforwardLoginMixin, MfAssetAllocationSpider):
    """``xmf_smtb`` variant 用 asset_allocation spider.

    URL/parser は ``MfAssetAllocationSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_smtb_asset_allocation"
    variant_name = "xmf_smtb"
