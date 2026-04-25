"""JSONL 読み込みユーティリティ (純関数).

JsonOutputPipeline が書き出した ``{spider}_{date:%Y%m%d}.jsonl`` を
glob で探索し、フィルタ条件で要素を絞り込む。
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


def load_spider_jsonl(
    output_dir: Path,
    spider_prefix: str,
) -> Iterator[dict]:
    """``output_dir`` 配下の ``{spider_prefix}_*.jsonl`` を全件読み出す.

    Parameters
    ----------
    output_dir : Path
        JsonOutputPipeline の出力ディレクトリ。
    spider_prefix : str
        ファイル名 prefix (例: ``mf_transaction``)。サニタイズ済みを想定。

    Yields
    ------
    dict
        各 JSONL 行。複数ファイルが存在する場合は ``mtime`` 昇順で結合。
    """
    if not output_dir.exists():
        return
    files = sorted(
        (
            p
            for p in output_dir.iterdir()
            if p.is_file()
            and p.name.startswith(f"{spider_prefix}_")
            and p.suffix == ".jsonl"
        ),
        key=lambda p: p.stat().st_mtime,
    )
    for f in files:
        yield from iter_jsonl(f)


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
