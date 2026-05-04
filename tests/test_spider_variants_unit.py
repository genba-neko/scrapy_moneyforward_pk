"""spiders.variants registry および 3 generic spider の variant 解決テスト."""

from __future__ import annotations

import pytest

from moneyforward.spiders.variants import VARIANTS, VariantConfig, get_variant


def test_variant_config_is_frozen():
    cfg = VARIANTS["mf"]
    with pytest.raises(Exception):  # noqa: B017,PT011 - frozen dataclass FrozenInstanceError
        cfg.name = "mutated"  # type: ignore[misc]


def test_variants_contains_mf_and_ssnb():
    assert "mf" in VARIANTS
    assert "xmf_ssnb" in VARIANTS
    assert isinstance(VARIANTS["mf"], VariantConfig)


def test_variants_contains_all_legacy_partner_sites():
    """元 PJ の 8 派生サイト + mf 本体 + xmf 一般 + xmf_ssnb = 11 variant 登録済."""
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
    if variant_name == "mf":
        assert cfg.login_form_email == "mfid_user[email]"
        assert cfg.is_partner_portal is False
    else:
        assert cfg.login_form_email == "sign_in_session_service[email]"
        assert cfg.is_partner_portal is True


def test_get_variant_unknown_raises_keyerror():
    with pytest.raises(KeyError, match="unknown variant"):
        get_variant("does_not_exist")


# --------------------------------------- 3 generic spider classes (T3 後)


def test_transaction_spider_default_resolves_mf():
    """site 省略時は ``variant_name = "mf"`` をデフォルトに解決."""
    from moneyforward.spiders.transaction import MfTransactionSpider

    spider = MfTransactionSpider()
    assert spider.name == "transaction"
    assert spider.spider_type == "transaction"
    assert spider.variant.name == "mf"
    assert spider.is_partner_portal is False
    assert spider.start_url == "https://moneyforward.com/"
    assert spider.allowed_domains == ["moneyforward.com"]


def test_transaction_spider_with_site_kwarg_targets_partner_portal():
    """``site`` kwarg で xmf_ssnb 等の派生サイト URL に切替."""
    from moneyforward.spiders.transaction import MfTransactionSpider

    spider = MfTransactionSpider(site="xmf_ssnb")
    assert spider.variant.name == "xmf_ssnb"
    assert spider.is_partner_portal is True
    assert spider.start_url == "https://ssnb.x.moneyforward.com/"
    assert spider.allowed_domains == ["ssnb.x.moneyforward.com"]
    req = spider._month_request(2025, 1)
    assert req.url == "https://ssnb.x.moneyforward.com/cf"


def test_account_spider_with_site_kwarg():
    from moneyforward.spiders.account import MfAccountSpider

    spider = MfAccountSpider(site="xmf_mizuho")
    assert spider.name == "account"
    assert spider.spider_type == "account"
    assert spider.variant.name == "xmf_mizuho"
    req = spider._accounts_request(is_update=False, attempt=0)
    assert req.url == "https://mizuho.x.moneyforward.com/accounts"


def test_asset_allocation_spider_with_site_kwarg():
    from moneyforward.spiders.asset_allocation import MfAssetAllocationSpider

    spider = MfAssetAllocationSpider(site="xmf_jabank")
    assert spider.name == "asset_allocation"
    assert spider.spider_type == "asset_allocation"
    assert spider.variant.name == "xmf_jabank"


def test_spider_login_credentials_kwargs_override_settings():
    """``login_user`` / ``login_pass`` kwarg で settings.py の env 値を上書き."""
    from moneyforward.spiders.transaction import MfTransactionSpider

    spider = MfTransactionSpider(
        site="mf",
        login_user="kwargs@example.com",
        login_pass="kwargs-pw",  # noqa: S106
    )
    assert spider.login_user == "kwargs@example.com"
    assert spider.login_pass == "kwargs-pw"


@pytest.mark.parametrize(
    "variant_name",
    [
        "xmf",
        "xmf_mizuho",
        "xmf_jabank",
        "xmf_smtb",
        "xmf_linkx",
        "xmf_okashin",
        "xmf_shiga",
        "xmf_shiz",
    ],
)
def test_each_partner_variant_resolves_through_transaction_spider(variant_name: str):
    """派生サイトの URL/フォームが registry 経由で取得可能."""
    from moneyforward.spiders.transaction import MfTransactionSpider

    spider = MfTransactionSpider(site=variant_name)
    assert spider.variant.name == variant_name
    assert spider.is_partner_portal is True
    req = spider._month_request(2025, 1)
    assert req.url == spider.variant.transactions_url


def test_scrapy_loader_lists_three_generic_spiders():
    """SpiderLoader で 3 spider (transaction / account / asset_allocation) を解決."""
    from scrapy.settings import Settings
    from scrapy.spiderloader import SpiderLoader

    settings = Settings({"SPIDER_MODULES": ["moneyforward.spiders"]})
    loader = SpiderLoader.from_settings(settings)
    names = set(loader.list())
    assert names == {"transaction", "account", "asset_allocation"}
