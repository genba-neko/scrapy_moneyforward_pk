"""分別管理資産・借入控除の定義読込と計算 (旧 PJ ``adjust_segregated_asset`` 相当).

旧 PJ でハードコードされていた ``period_dict`` / ``period_dict_debt`` を
外部 YAML に切り出し、純関数で計算する。

YAML スキーマ (config/segregated_asset.example.yaml 参照):
    segregated: [{period: [start, end|"unlimited"], asset_class: str, amount: int, note: str}]
    debt:        [{period: [start, end|"unlimited"], asset_class: str, amount: int, note: str}]

期間:
  - period[0]: 開始日 (YYYY-MM-DD)。"unlimited" は不可。
  - period[1]: 終了日 (YYYY-MM-DD) または "unlimited"。
  - クォートなし YAML 日付 (e.g. 2023-01-01) も受け付ける (PyYAML が date 型で渡す)。
  - start > end は ValueError。
  - 境界は両端込み (start <= target <= end)。

note フィールドは任意。str 以外の場合は ValueError。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from moneyforward.reports.asset_allocation import ASSET_CLASSES

_DATE_FMT = "%Y-%m-%d"
_UNLIMITED = "unlimited"
_ALLOWED_TOP_KEYS = frozenset({"segregated", "debt"})

logger = logging.getLogger(__name__)


def _parse_date(value: Any, label: str) -> date:
    """YAML 値を date に変換する。str (YYYY-MM-DD) または date オブジェクトを受け付ける."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value)
    try:
        return datetime.strptime(s, _DATE_FMT).date()
    except ValueError:
        raise ValueError(f"{label}: invalid date '{s}' (expected YYYY-MM-DD)") from None


def load_segregated_config(path: Path) -> dict[str, list[dict]]:
    """YAML を読み込み検証済みの config dict を返す.

    ファイル不在時は空の config (no-op) を返す。
    スキーマ違反は ValueError を送出する。

    Returns
    -------
    dict
        ``{"segregated": [...], "debt": [...]}``
    """
    if not path.exists():
        return {"segregated": [], "debt": []}

    with path.open(encoding="utf-8") as f:
        raw: Any = yaml.safe_load(f)

    if raw is None:
        return {"segregated": [], "debt": []}

    if not isinstance(raw, dict):
        raise ValueError(
            f"segregated_asset YAML must be a mapping at the top level, got {type(raw).__name__}"
        )

    unknown_keys = set(raw.keys()) - _ALLOWED_TOP_KEYS
    if unknown_keys:
        raise ValueError(
            f"Unknown top-level keys in segregated_asset YAML: {sorted(unknown_keys)}. "
            f"Allowed: {sorted(_ALLOWED_TOP_KEYS)}"
        )

    result: dict[str, list[dict]] = {"segregated": [], "debt": []}
    for key in ("segregated", "debt"):
        entries = raw.get(key) or []
        if not isinstance(entries, list):
            raise ValueError(f"'{key}' must be a list")
        for i, entry in enumerate(entries):
            _validate_entry(entry, key, i)
        result[key] = entries

    return result


def _validate_entry(entry: Any, key: str, idx: int) -> None:
    prefix = f"{key}[{idx}]"
    if not isinstance(entry, dict):
        raise ValueError(f"{prefix}: entry must be a mapping")

    period = entry.get("period")
    if not isinstance(period, list) or len(period) != 2:
        raise ValueError(
            f"{prefix}.period: must be a 2-element list [start, end|unlimited]"
        )

    start_raw = period[0]
    if str(start_raw) == _UNLIMITED:
        raise ValueError(f"{prefix}.period[0]: start date cannot be 'unlimited'")
    start_date = _parse_date(start_raw, f"{prefix}.period[0]")

    end_raw = period[1]
    end_date: date | None = None
    if str(end_raw) != _UNLIMITED:
        end_date = _parse_date(end_raw, f"{prefix}.period[1]")

    if end_date is not None and start_date > end_date:
        raise ValueError(
            f"{prefix}.period: start '{start_date}' is after end '{end_date}'"
        )

    asset_class = entry.get("asset_class")
    if asset_class not in ASSET_CLASSES:
        raise ValueError(
            f"{prefix}.asset_class: '{asset_class}' is not a valid asset class. "
            f"Valid: {list(ASSET_CLASSES)}"
        )

    amount = entry.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise ValueError(
            f"{prefix}.amount: must be an integer (not bool/float), got {type(amount).__name__}"
        )

    note = entry.get("note")
    if note is not None and not isinstance(note, str):
        raise ValueError(f"{prefix}.note: must be a string, got {type(note).__name__}")


def compute_adjustments(
    config: dict[str, list[dict]], target: date
) -> dict[str, dict[str, int]]:
    """期間定義から target 日付に有効なエントリを集計する.

    Parameters
    ----------
    config:
        ``load_segregated_config`` の戻り値。
    target:
        集計対象日付。

    Returns
    -------
    dict
        ``{"segregated": {asset_class: int}, "debt": {asset_class: int}}``
    """
    result: dict[str, dict[str, int]] = {"segregated": {}, "debt": {}}
    for key in ("segregated", "debt"):
        acc: dict[str, int] = {}
        for entry in config.get(key, []):
            start_raw = entry["period"][0]
            start = _parse_date(start_raw, "period[0]")

            end_raw = entry["period"][1]
            end: date | None = (
                None
                if str(end_raw) == _UNLIMITED
                else _parse_date(end_raw, "period[1]")
            )

            in_range = (end is None and start <= target) or (
                end is not None and start <= target <= end
            )
            if not in_range:
                continue

            asset_class: str = entry["asset_class"]
            acc[asset_class] = acc.get(asset_class, 0) + int(entry["amount"])
        result[key] = acc
    return result


def apply_adjustments(aggregated: dict, adjustments: dict[str, dict[str, int]]) -> dict:
    """aggregate_asset_allocation の戻り値に分別管理・借入控除を適用する.

    元の dict を変更せず新 dict を返す (純関数)。

    segregated: ``aggregated["separate"]`` に合算する。total / classes は変えない。
    debt:       ``aggregated["total"]`` と ``aggregated["classes"][asset_class]`` から減算する。

    Parameters
    ----------
    aggregated:
        ``aggregate_asset_allocation`` の戻り値。
    adjustments:
        ``compute_adjustments`` の戻り値。

    Returns
    -------
    dict
        補正後の aggregated dict。
    """
    result = {
        "total": aggregated["total"],
        "separate": aggregated.get("separate", 0),
        "classes": dict(aggregated["classes"]),
        "unknown": aggregated.get("unknown", []),
    }

    segregated_sum = sum(adjustments.get("segregated", {}).values())
    result["separate"] += segregated_sum

    for asset_class, amount in adjustments.get("debt", {}).items():
        result["total"] -= amount
        if asset_class not in result["classes"]:
            raise KeyError(
                f"apply_adjustments: debt asset_class '{asset_class}' not found in aggregated['classes']. "
                f"Available: {list(result['classes'].keys())}"
            )
        result["classes"][asset_class] -= amount

    return result
