"""アセットアロケーション集計レポート (元 PJ ``get_asset_allocation_report`` 相当).

JSONL の asset_allocation レコードを ``asset_type`` / ``asset_item_key`` で
分類し、生活費 / 現金 / 待機資金 / 投資信託 / 株式 / 債券 / FX / その他 等の
アセットクラスへ集計する純関数。
"""

from __future__ import annotations

from typing import Iterable

# アセットクラス順序固定 (元 PJ ``MoneyforwardAssetAllocation.__init__`` 準拠)
ASSET_CLASSES: tuple[str, ...] = (
    "生活費",
    "現金",
    "待機資金",
    "投資信託",
    "株式（長期）",
    "株式（短期）",
    "債券",
    "FX",
    "先物・オプション",
    "その他の資産",
)

# asset_item_key prefix → 生活費扱いとなるパターン (元 PJ ``aggregate_asset_allocation``)
_LIFE_DEPO_PREFIXES: tuple[str, ...] = (
    "mf_asset_allocation-service@",
    "mf_asset_allocation-finance@",
    "xmf_jabank_asset_allocation-service@",
    "xmf_jabank_asset_allocation-finance@",
    "xmf_linkx_asset_allocation-service@",
    "xmf_linkx_asset_allocation-finance@",
)
# 静岡銀行系の現金は待機資金扱い
_STANDBY_DEPO_PREFIXES: tuple[str, ...] = (
    "xmf_shiz_asset_allocation-service@",
    "xmf_shiz_asset_allocation-finance@",
)


def _classify(item: dict) -> str | None:
    """1 件の asset_allocation を どの asset_class に振るか決定する.

    元 PJ ``aggregate_asset_allocation`` の if/elif 連鎖を素直に移植した
    純関数。マッチしない場合は ``None`` を返す。

    Parameters
    ----------
    item : dict
        ``MoneyforwardAssetAllocationItem`` の dict 表現。

    Returns
    -------
    str | None
        振り分け先アセットクラス名。
    """
    asset_type = item.get("asset_type", "")
    asset_item_key = item.get("asset_item_key", "")
    asset_name = item.get("asset_name", "")

    if asset_type == "portfolio_det_depo":
        for prefix in _LIFE_DEPO_PREFIXES:
            if prefix in asset_item_key:
                return "生活費"
        for prefix in _STANDBY_DEPO_PREFIXES:
            if prefix in asset_item_key:
                return "待機資金"
        return "現金"
    if "株式" in asset_name and "xmf_shiz" in asset_item_key:
        return "待機資金"
    if asset_type == "portfolio_det_po":
        return "生活費"
    if asset_type == "portfolio_det_eq":
        return "株式（長期）"
    if asset_type == "portfolio_det_mgn":
        return "株式（短期）"
    if asset_type == "portfolio_det_mf":
        return "投資信託"
    if asset_type == "portfolio_det_bd":
        return "債券"
    if asset_type == "portfolio_det_fx":
        return "FX"
    if asset_type == "portfolio_det_drv":
        return "先物・オプション"
    if asset_type == "portfolio_det_oth":
        return "その他の資産"
    return None


def aggregate_asset_allocation(items: Iterable[dict]) -> dict:
    """資産配分を集計する.

    Parameters
    ----------
    items : Iterable[dict]
        ``MoneyforwardAssetAllocationItem`` の dict 表現。

    Returns
    -------
    dict
        ``{"total": int, "classes": {asset_class: int}, "unknown": [...]}``。
    """
    classes: dict[str, int] = {name: 0 for name in ASSET_CLASSES}
    total = 0
    unknown: list[dict] = []
    for item in items:
        amount_raw = item.get("amount_value", 0)
        try:
            amount = int(amount_raw)
        except (TypeError, ValueError):
            amount = int(str(amount_raw).replace(",", "") or 0)
        total += amount
        klass = _classify(item)
        if klass is None:
            unknown.append(item)
            continue
        classes[klass] += amount
    return {"total": total, "classes": classes, "unknown": unknown, "separate": 0}


def report_message(aggregated: dict, year: int, month: int, day: int) -> str:
    """集計結果を Slack 風テキストに整形する (元 PJ ``report_message`` 相当).

    Parameters
    ----------
    aggregated : dict
        ``aggregate_asset_allocation`` の戻り値。
    year, month, day : int
        対象日付 (見出し用)。

    Returns
    -------
    str
        改行を含む Slack 投稿向けテキスト。総資産 0 円の場合は割合を
        ``---`` で表示し ZeroDivision を避ける。
    """
    total = aggregated["total"]
    classes = aggregated["classes"]
    separate = aggregated.get("separate", 0)

    lines: list[str] = []
    lines.append(f"{'アセットアロケーション':*^10} ({year}/{month}/{day})")
    lines.append(f"総資産額={total:,}円")
    lines.append(f"（分別管理資産={separate:,}円）")
    for name in ASSET_CLASSES:
        value = classes.get(name, 0)
        if total != 0:
            percent: int | str = int((value / total) * 100)
        else:
            percent = "---"
        lines.append(f"{name}={value:,}円 ({percent}%)")
    return "\n".join(lines) + "\n"
