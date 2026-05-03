"""Pure HTML → Item parsers. Kept out of spider classes for unit testing.

Selectors are ported verbatim from the legacy scrapy_moneyforward project so
the JSON Lines record shape stays identical to the legacy DynamoDB schema.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Iterator

from scrapy.http import Response

from moneyforward_pk.items import (
    MoneyforwardAccountItem,
    MoneyforwardAssetAllocationItem,
    MoneyforwardTransactionItem,
)

_DATE_SORT_RE = re.compile(r"(\d{4})/(\d+)/(\d+)-\d+")
_ACCOUNT_TRIM_RE = re.compile(r"^(.+?)\(本サイト\).*")


def _join_strip(texts) -> str:
    r"""Mirror legacy ``MfSpider.join_strip`` (mf_transaction.py:271).

    Concatenates text fragments and removes ``\n``, ``\t``, ``,`` plus
    leading/trailing whitespace. Used by ``parse_accounts`` so that the
    SHA256 input for ``account_item_key`` is byte-identical to the legacy
    DynamoDB SK values.
    """
    if texts is None:
        return ""
    if isinstance(texts, str):
        texts = [texts]
    return "".join(texts).replace("\n", "").replace("\t", "").replace(",", "").strip()


def parse_transactions(
    response: Response, year: int, month: int
) -> Iterator[MoneyforwardTransactionItem]:
    """Yield transaction items from a /cf monthly page.

    Notes
    -----
    The legacy MoneyForward markup applies ``class="transaction_list"`` to the
    ``<tr>`` rows directly. Some captures wrap rows in a parent element bearing
    that class. Both shapes are accepted via the union selector below; rows are
    de-duplicated by Selector identity to avoid double yields when a single row
    matches both legs.
    """
    year_month = f"{year:04d}{month:02d}"
    seen_ids: set[int] = set()
    rows = list(response.css("tr.transaction_list")) + list(
        response.css(".transaction_list tr")
    )
    for row in rows:
        row_id = id(row.root)
        if row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        sort_value = row.css("td.date::attr(data-table-sortable-value)").get()
        if not sort_value:
            continue
        m = _DATE_SORT_RE.match(sort_value)
        if not m:
            continue
        y, mo, d = (int(g) for g in m.groups())

        # Restrict to the row itself: legacy markup applies the
        # ``target-active`` class to the <tr>, never to nested children.
        # Using a descendant selector here previously misclassified rows
        # whose nested controls happened to carry the same class.
        is_active = "target-active" in (row.attrib.get("class") or "")
        date_text = row.css("td.date span::text").get(default="").strip()
        content = row.css("td.content span::text").get(default="").strip()
        amount_view = row.css("td.amount span::text").get(default="").strip()
        amount_number = _parse_amount(amount_view)

        account, transfer, detail = _extract_account_cells(row)

        lctg = row.css("td.lctg a::text").get(default="未分類").strip() or "未分類"
        mctg = row.css("td.mctg a::text").get(default="未分類").strip() or "未分類"
        memo = row.css("td.memo span::text").get(default="").strip()

        yield MoneyforwardTransactionItem(
            year_month=year_month,
            is_active=is_active,
            data_table_sortable_value=sort_value,
            year=y,
            month=mo,
            day=d,
            date=date_text,
            content=content,
            amount_number=amount_number,
            amount_view=amount_view,
            transaction_account=account,
            transaction_transfer=transfer,
            transaction_detail=detail,
            lctg=lctg,
            mctg=mctg,
            memo=memo,
        )


def _parse_amount(view: str) -> int:
    if not view:
        return 0
    cleaned = view.replace(",", "").replace("円", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _extract_account_cells(row) -> tuple[str, str, str]:
    """Return (account, transfer, detail) respecting manual/auto/transfer shapes."""
    manual = row.css("td.sub_account_id_hash span::text").get()
    if manual:
        return manual.strip(), "", ""

    auto = row.css("td.note.calc")
    if auto:
        account = auto.css("::text").get(default="").strip()
        detail = auto.css("::attr(data-original-title)").get(default="").strip()
        return account, "", detail

    # Take all td.calc cells and filter out ones whose data-original-title is
    # empty in Python. The :not([data-original-title=""]) CSS form was brittle
    # because cells without the attribute at all were also excluded; the
    # explicit Python filter accepts both shapes.
    for cell in row.css("td.calc"):
        detail = cell.css("::attr(data-original-title)").get(default="").strip()
        if not detail:
            continue
        account = (
            cell.css(".transfer_account_box_02 a::text").get()
            or cell.css("::text").get(default="")
        ).strip()
        transfer = cell.css(".transfer_account_box::text").get(default="").strip()
        return account, transfer, detail

    return "", "", ""


def parse_asset_allocation(
    response: Response, spider_name: str, login_user: str, today: date | None = None
) -> Iterator[MoneyforwardAssetAllocationItem]:
    """Yield asset-allocation items from /bs/portfolio first table."""
    today = today or date.today()
    year_month_day = today.strftime("%Y%m%d")

    # Legacy spec: only the first <table> on /bs/portfolio carries asset rows.
    # Subsequent tables are summary/footer markup that must not leak through.
    tables = response.css("table")
    if not tables:
        return
    first_table = tables[0]
    for row in first_table.xpath(".//tr"):
        asset_name = row.css("th a::text").get()
        if not asset_name:
            continue
        asset_name = asset_name.strip()
        href = row.css("th a::attr(href)").get(default="")
        asset_type = href.split("#", 1)[-1] if "#" in href else ""
        amount_view = row.css("td::text").get(default="").strip()
        amount_value = _parse_amount(amount_view)

        asset_item_key = f"{spider_name}-{login_user}-{asset_type}"

        yield MoneyforwardAssetAllocationItem(
            year_month_day=year_month_day,
            asset_item_key=asset_item_key,
            year=today.year,
            month=today.month,
            day=today.day,
            date=today.strftime("%Y/%m/%d"),
            asset_name=asset_name,
            asset_type=asset_type,
            amount_view=amount_view,
            amount_value=amount_value,
        )


def parse_accounts(
    response: Response, today: date | None = None
) -> tuple[list[MoneyforwardAccountItem], bool]:
    """Parse /accounts page.

    Returns (items, is_updating) — the caller re-polls while is_updating=True.
    """
    today = today or date.today()
    year_month_day = today.strftime("%Y%m%d")

    # Locate the account table by its header label and walk one ancestor::tr
    # rather than two ``parent::node()`` hops. Single ``ancestor::tr[1]`` is
    # robust to extra wrapper nodes (legacy markup wrapped <th> in <span>).
    table_rows = response.xpath(
        '//th[contains(text(), "金融機関")]/ancestor::tr[1]/ancestor::table[1]//tr'
    )
    items: list[MoneyforwardAccountItem] = []
    is_updating = False

    for row in table_rows:
        tds = row.xpath("./td")
        if len(tds) < 4:
            continue

        # Use ``*::text`` + join_strip to mirror legacy ``mf_account.py:159``
        # exactly (descendant text + ``\n``/``\t``/``,`` removal). The SHA256
        # input below must be byte-identical to legacy or the resulting SK
        # diverges from what's already stored in DynamoDB.
        raw_name = _join_strip(tds[0].css("*::text").getall())
        if not raw_name:
            continue
        m = _ACCOUNT_TRIM_RE.match(raw_name)
        account_name = m.group(1).strip() if m else raw_name
        account_item_key = hashlib.sha256(raw_name.encode("utf-8")).hexdigest()

        amount_number = _join_strip(tds[1].css("*::text").getall())
        account_date = _join_strip(tds[2].css("*::text").getall())

        status_spans = (
            tds[3]
            .css(
                'span[id^="js-status-sentence-span-"]:not([id^="js-hidden-status-sentence-span"])::text'
            )
            .getall()
        )
        account_status = " ".join(s.strip() for s in status_spans if s.strip())

        if "更新中" in account_status:
            is_updating = True

        items.append(
            MoneyforwardAccountItem(
                year_month_day=year_month_day,
                account_item_key=account_item_key,
                account_name=account_name,
                account_amount_number=amount_number,
                account_date=account_date,
                account_status=account_status,
            )
        )

    return items, is_updating
