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


def test_variants_contains_all_legacy_partner_sites():
    """元 PJ の 8 派生サイト + mf 本体 + xmf_ssnb = 10 variant 登録済."""
    expected = {
        "mf",
        "xmf",
        "xmf_ssnb",
        "xmf_mizuho",
        "xmf_jabank",
        "xmf_smtb",
        "xmf_linkx",
        "xmf_okashin",
        "xmf_shiga",
        "xmf_shiz",
    }
    assert expected <= set(VARIANTS)


@pytest.mark.parametrize("variant_name", sorted(VARIANTS.keys()))
def test_each_variant_url_consistency(variant_name: str):
    """各 variant の URL が base_url の host と一致し、login form 名が許容値."""
    cfg = get_variant(variant_name)
    base_host = cfg.base_url.replace("https://", "").rstrip("/")
    for url in (cfg.accounts_url, cfg.transactions_url, cfg.asset_allocation_url):
        assert base_host in url, f"{variant_name}: {url} not under {base_host}"
    # mf のみ mfid_user, それ以外は sign_in_session_service.
    if variant_name == "mf":
        assert cfg.login_form_email == "mfid_user[email]"
        assert cfg.is_partner_portal is False
    else:
        assert cfg.login_form_email == "sign_in_session_service[email]"
        assert cfg.is_partner_portal is True


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


def test_mf_transaction_spider_uses_variant_url():
    """``MfTransactionSpider`` は variant.transactions_url を request URL に使う."""
    from moneyforward_pk.spiders.transaction import MfTransactionSpider

    spider = MfTransactionSpider()
    req = spider._month_request(2025, 1)
    assert req.url == "https://moneyforward.com/cf"
    assert spider.allowed_domains == ["moneyforward.com"]


def test_mf_account_spider_uses_variant_url():
    """``MfAccountSpider`` は variant.accounts_url を request URL に使う."""
    from moneyforward_pk.spiders.account import MfAccountSpider

    spider = MfAccountSpider()
    req = spider._accounts_request(is_update=False, attempt=0)
    assert req.url == "https://moneyforward.com/accounts"
    assert spider.allowed_domains == ["moneyforward.com"]


def test_xmf_ssnb_transaction_uses_partner_url():
    """xmf_ssnb spider は ssnb.x.moneyforward.com 配下の URL を発行する."""
    spider = XmfSsnbTransactionSpider()
    req = spider._month_request(2025, 1)
    assert req.url == "https://ssnb.x.moneyforward.com/cf"
    assert spider.allowed_domains == ["ssnb.x.moneyforward.com"]
    assert spider.start_url == "https://ssnb.x.moneyforward.com/"


# 派生サイト 8 系統 (xmf 含む) × 3 spider type の登録確認.
_DERIVED_VARIANTS = [
    "xmf",
    "xmf_mizuho",
    "xmf_jabank",
    "xmf_smtb",
    "xmf_linkx",
    "xmf_okashin",
    "xmf_shiga",
    "xmf_shiz",
]


@pytest.mark.parametrize("variant_name", _DERIVED_VARIANTS)
def test_derived_transaction_spider_registers(variant_name: str):
    """各派生サイトの transaction spider が import 可能で variant URL を解決."""
    module = __import__(
        f"moneyforward_pk.spiders.{variant_name}_transaction",
        fromlist=["*"],
    )
    spider_cls_name = next(
        n
        for n in dir(module)
        if n.endswith("TransactionSpider") and n != "MfTransactionSpider"
    )
    spider = getattr(module, spider_cls_name)()
    assert spider.name == f"{variant_name}_transaction"
    assert spider.variant.name == variant_name
    req = spider._month_request(2025, 1)
    assert variant_name.replace("xmf_", "").replace(
        "xmf", "x"
    ) in req.url or req.url.startswith(spider.variant.base_url)


@pytest.mark.parametrize("variant_name", _DERIVED_VARIANTS)
def test_derived_account_spider_registers(variant_name: str):
    module = __import__(
        f"moneyforward_pk.spiders.{variant_name}_account",
        fromlist=["*"],
    )
    spider_cls_name = next(
        n for n in dir(module) if n.endswith("AccountSpider") and n != "MfAccountSpider"
    )
    spider = getattr(module, spider_cls_name)()
    assert spider.name == f"{variant_name}_account"
    assert spider.variant.name == variant_name
    req = spider._accounts_request(is_update=False, attempt=0)
    assert req.url == spider.variant.accounts_url


@pytest.mark.parametrize("variant_name", _DERIVED_VARIANTS)
def test_derived_asset_allocation_spider_registers(variant_name: str):
    module = __import__(
        f"moneyforward_pk.spiders.{variant_name}_asset_allocation",
        fromlist=["*"],
    )
    spider_cls_name = next(
        n
        for n in dir(module)
        if n.endswith("AssetAllocationSpider") and n != "MfAssetAllocationSpider"
    )
    spider = getattr(module, spider_cls_name)()
    assert spider.name == f"{variant_name}_asset_allocation"
    assert spider.variant.name == variant_name


def test_scrapy_loader_lists_all_thirty_spiders():
    """``scrapy list`` 相当の SpiderLoader で 30 spider 全数登録を確認."""
    from scrapy.settings import Settings
    from scrapy.spiderloader import SpiderLoader

    settings = Settings({"SPIDER_MODULES": ["moneyforward_pk.spiders"]})
    loader = SpiderLoader.from_settings(settings)
    names = set(loader.list())
    # 10 variant × 3 spider type = 30
    assert len(names) >= 30
    # mf / xmf / xmf_ssnb / 7 派生 = 10 variants. 各 transaction が必須.
    for variant in [
        "mf",
        "xmf",
        "xmf_ssnb",
        "xmf_mizuho",
        "xmf_jabank",
        "xmf_smtb",
        "xmf_linkx",
        "xmf_okashin",
        "xmf_shiga",
        "xmf_shiz",
    ]:
        assert f"{variant}_transaction" in names
        assert f"{variant}_account" in names
        assert f"{variant}_asset_allocation" in names
