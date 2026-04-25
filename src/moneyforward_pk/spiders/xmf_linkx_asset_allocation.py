"""linkx家計簿 (linkx.x.moneyforward.com) 派生 Moneyforward の資産配分スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.asset_allocation import MfAssetAllocationSpider
from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin


class XmfLinkxAssetAllocationSpider(XMoneyforwardLoginMixin, MfAssetAllocationSpider):
    """``xmf_linkx`` variant 用 asset_allocation spider.

    URL/parser は ``MfAssetAllocationSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_linkx_asset_allocation"
    variant_name = "xmf_linkx"
