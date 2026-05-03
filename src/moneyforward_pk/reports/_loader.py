"""出力 JSON 読み込みユーティリティ (純関数).

crawl_runner が書き出した ``moneyforward_{spider_type}.json`` (JSON 配列) を
読み込み、フィルタ条件で要素を絞り込む。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator


def iter_jsonl(path: Path) -> Iterator[dict]:
    """1 件の JSONL ファイルを行単位で読み出す.

    Parameters
    ----------
    path : Path
        対象 JSONL ファイル。

    Yields
    ------
    dict
        各行をパースした結果。空行はスキップする。

    Notes
    -----
    破損行は ``json.JSONDecodeError`` を伝播する。呼び出し側で
    必要に応じて捕捉する。
    """
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            yield json.loads(stripped)


def load_output_json(
    output_dir: Path,
    spider_type: str,
) -> Iterator[dict]:
    """``output_dir/moneyforward_{spider_type}.json`` を全件読み出す.

    Parameters
    ----------
    output_dir : Path
        crawl_runner の出力ディレクトリ。
    spider_type : str
        spider 種別 (例: ``transaction``, ``asset_allocation``)。

    Yields
    ------
    dict
        JSON 配列の各要素。ファイルが存在しない場合は空イテレータ。
    """
    path = output_dir / f"moneyforward_{spider_type}.json"
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    yield from data


def filter_year_month(items: Iterable[dict], year: int, month: int) -> Iterator[dict]:
    """``year_month`` フィールドが ``YYYYMM`` 一致するレコードを抽出する.

    Parameters
    ----------
    items : Iterable[dict]
        トランザクション系レコード。
    year, month : int
        対象年月。

    Yields
    ------
    dict
        条件一致レコード。
    """
    target = f"{year:04d}{month:02d}"
    for item in items:
        if str(item.get("year_month", "")) == target:
            yield item


def filter_year_month_day(
    items: Iterable[dict], year: int, month: int, day: int
) -> Iterator[dict]:
    """``year_month_day`` が ``YYYYMMDD`` 一致するレコードを抽出する."""
    target = f"{year:04d}{month:02d}{day:02d}"
    for item in items:
        if str(item.get("year_month_day", "")) == target:
            yield item
