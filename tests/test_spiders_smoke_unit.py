"""Smoke test: 3 generic spider classes importable, names wired."""

from __future__ import annotations


def test_spider_imports_and_names():
    from moneyforward_pk.spiders.account import MfAccountSpider
    from moneyforward_pk.spiders.asset_allocation import MfAssetAllocationSpider
    from moneyforward_pk.spiders.transaction import MfTransactionSpider

    assert MfTransactionSpider.name == "transaction"
    assert MfAssetAllocationSpider.name == "asset_allocation"
    assert MfAccountSpider.name == "account"


def test_scrapy_spider_loader_picks_up_three_generic_spiders():
    from scrapy.settings import Settings
    from scrapy.spiderloader import SpiderLoader

    settings = Settings({"SPIDER_MODULES": ["moneyforward_pk.spiders"]})
    loader = SpiderLoader.from_settings(settings)
    names = set(loader.list())
    assert {"transaction", "asset_allocation", "account"} <= names
