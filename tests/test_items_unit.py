"""Items: fields present, dict conversion works."""

from __future__ import annotations

from moneyforward.items import (
    MoneyforwardAccountItem,
    MoneyforwardAssetAllocationItem,
    MoneyforwardTransactionItem,
)


def test_transaction_item_fields():
    item = MoneyforwardTransactionItem(
        year_month="202501",
        is_active=True,
        data_table_sortable_value="2025/01/15-001",
        year=2025,
        month=1,
        day=15,
        date="01/15",
        content="スーパー購入",
        amount_number=-1234,
        amount_view="-1,234円",
        transaction_account="クレカA",
        transaction_transfer="",
        transaction_detail="",
        lctg="食費",
        mctg="食料品",
        memo="",
    )
    d = dict(item)
    assert d["year_month"] == "202501"
    assert d["amount_number"] == -1234


def test_asset_allocation_item_fields():
    item = MoneyforwardAssetAllocationItem(
        year_month_day="20250115",
        asset_item_key="mf_asset_allocation-user-portfolio_det_depo",
        year=2025,
        month=1,
        day=15,
        date="2025/01/15",
        asset_name="預金・現金・仮想通貨",
        asset_type="portfolio_det_depo",
        amount_view="246,151円",
        amount_value=246151,
    )
    assert dict(item)["amount_value"] == 246151


def test_account_item_fields():
    item = MoneyforwardAccountItem(
        year_month_day="20250115",
        account_item_key="abc123",
        account_name="みずほ銀行",
        account_amount_number="12,345円",
        account_date="2025/01/15",
        account_status="正常",
    )
    assert dict(item)["account_name"] == "みずほ銀行"
