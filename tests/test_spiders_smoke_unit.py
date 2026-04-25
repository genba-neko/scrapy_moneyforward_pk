"""Smoke test: spider classes importable, names wired, settings honored."""

from __future__ import annotations


def test_spider_imports_and_names():
    from moneyforward_pk.spiders.account import MfAccountSpider
    from moneyforward_pk.spiders.asset_allocation import MfAssetAllocationSpider
    from moneyforward_pk.spiders.transaction import MfTransactionSpider

    assert MfTransactionSpider.name == "mf_transaction"
    assert MfAssetAllocationSpider.name == "mf_asset_allocation"
    assert MfAccountSpider.name == "mf_account"


def test_scrapy_spider_loader_picks_up_all_three():
    from scrapy.settings import Settings
    from scrapy.spiderloader import SpiderLoader

    settings = Settings({"SPIDER_MODULES": ["moneyforward_pk.spiders"]})
    loader = SpiderLoader.from_settings(settings)
    names = set(loader.list())
    assert {"mf_transaction", "mf_asset_allocation", "mf_account"} <= names
