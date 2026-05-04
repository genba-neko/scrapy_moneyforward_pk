"""Scrapy Items for MoneyForward scraping."""

from __future__ import annotations

import scrapy


class MoneyforwardTransactionItem(scrapy.Item):
    """Single transaction row from /cf page."""

    year_month = scrapy.Field()  # partition key, "YYYYMM"
    is_active = scrapy.Field()
    data_table_sortable_value = scrapy.Field()  # range key
    year = scrapy.Field()
    month = scrapy.Field()
    day = scrapy.Field()
    date = scrapy.Field()
    content = scrapy.Field()
    amount_number = scrapy.Field()
    amount_view = scrapy.Field()
    transaction_account = scrapy.Field()
    transaction_transfer = scrapy.Field()
    transaction_detail = scrapy.Field()
    lctg = scrapy.Field()
    mctg = scrapy.Field()
    memo = scrapy.Field()


class MoneyforwardAssetAllocationItem(scrapy.Item):
    """Asset allocation row from /bs/portfolio page."""

    year_month_day = scrapy.Field()  # partition key, "YYYYMMDD"
    asset_item_key = scrapy.Field()  # range key
    year = scrapy.Field()
    month = scrapy.Field()
    day = scrapy.Field()
    date = scrapy.Field()
    asset_name = scrapy.Field()
    asset_type = scrapy.Field()
    amount_view = scrapy.Field()
    amount_value = scrapy.Field()


class MoneyforwardAccountItem(scrapy.Item):
    """Account row from /accounts page."""

    year_month_day = scrapy.Field()  # partition key
    account_item_key = scrapy.Field()  # range key (sha256 of name)
    account_name = scrapy.Field()
    account_amount_number = scrapy.Field()
    account_date = scrapy.Field()
    account_status = scrapy.Field()
