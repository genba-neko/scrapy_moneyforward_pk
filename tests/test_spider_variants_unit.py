"""spiders.variants registry および xmf_ssnb 雛形 spider のテスト."""

from __future__ import annotations

import pytest

from moneyforward_pk.spiders.variants import VARIANTS, VariantConfig, get_variant
from moneyforward_pk.spiders.xmf_ssnb_transaction import XmfSsnbTransactionSpider


def test_variant_config_is_frozen():
    cfg = VARIANTS["mf"]
    with pytest.raises(Exception):  # noqa: B017,PT011 - frozen dataclass FrozenInstanceError
        cfg.name = "mutated"  # type: ignore[misc]


def test_variants_contains_mf_and_ssnb():
    assert "mf" in VARIANTS
    assert "xmf_ssnb" in VARIANTS
    assert isinstance(VARIANTS["mf"], VariantConfig)


def test_mf_variant_matches_legacy_urls():
    cfg = get_variant("mf")
    assert cfg.base_url == "https://moneyforward.com/"
    assert cfg.transactions_url == "https://moneyforward.com/cf"
    assert cfg.is_partner_portal is False
    assert cfg.login_form_email == "mfid_user[email]"


def test_xmf_ssnb_uses_partner_portal_form():
    cfg = get_variant("xmf_ssnb")
    assert cfg.is_partner_portal is True
    assert cfg.login_form_email == "sign_in_session_service[email]"
    assert "ssnb.x.moneyforward.com" in cfg.base_url


def test_get_variant_unknown_raises_keyerror():
    with pytest.raises(KeyError, match="unknown variant"):
        get_variant("does_not_exist")


def test_xmf_ssnb_spider_resolves_variant():
    spider = XmfSsnbTransactionSpider()
    assert spider.name == "xmf_ssnb_transaction"
    assert spider.variant.name == "xmf_ssnb"
    assert spider.is_partner_portal is True
    assert spider.start_url == "https://ssnb.x.moneyforward.com/"


def test_xmf_ssnb_spider_inherits_login_mixin_and_base():
    """既存 MfTransactionSpider 機能と XMoneyforwardLoginMixin の両方を継承."""
    from moneyforward_pk.spiders.base.moneyforward_base import (
        MoneyforwardBase,
        XMoneyforwardLoginMixin,
    )
    from moneyforward_pk.spiders.transaction import MfTransactionSpider

    assert issubclass(XmfSsnbTransactionSpider, MfTransactionSpider)
    assert issubclass(XmfSsnbTransactionSpider, MoneyforwardBase)
    assert issubclass(XmfSsnbTransactionSpider, XMoneyforwardLoginMixin)
