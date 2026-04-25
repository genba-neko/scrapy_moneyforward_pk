"""みずほ銀行 (mizuho.x.moneyforward.com) 派生 Moneyforward の資産配分スパイダー."""

from __future__ import annotations

from moneyforward_pk.spiders.asset_allocation import MfAssetAllocationSpider
from moneyforward_pk.spiders.base.moneyforward_base import XMoneyforwardLoginMixin


class XmfMizuhoAssetAllocationSpider(XMoneyforwardLoginMixin, MfAssetAllocationSpider):
    """``xmf_mizuho`` variant 用 asset_allocation spider.

    URL/parser は ``MfAssetAllocationSpider`` から継承し、
    ``XMoneyforwardLoginMixin`` で partner-portal のログインフローを上書きする.
    """

    name = "xmf_mizuho_asset_allocation"
    variant_name = "xmf_mizuho"
