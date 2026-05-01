"""crawl_runner のコアロジック (reactor 非依存部分).

Notes
-----
このモジュールは ``crawl_runner.py`` から切り出した pure Python ロジックを
保持する。``install_reactor`` を import 時に呼ばないため、pytest からは
本モジュールを安全に import できる。Twisted 依存は ``run_all`` 関数内で
ローカル import する。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from moneyforward_pk.spiders.variants.registry import VARIANTS

logger = logging.getLogger(__name__)

SPIDER_TYPES: tuple[str, ...] = ("transaction", "account", "asset_allocation")
OUTPUT_FILENAME_TEMPLATE = "moneyforward_{spider_type}.json"


@dataclass(frozen=True)
class Account:
    """1 アカウント分のログイン情報."""

    user: str
    password: str


@dataclass(frozen=True)
class Invocation:
    """spider 1 起動分のパラメータ.

    Attributes
    ----------
    site : str
        VARIANTS のキー (e.g., ``"mf"``, ``"xmf_ssnb"``).
    spider_type : str
        spider 種別 (``"transaction"`` / ``"account"`` / ``"asset_allocation"``).
    user : str
        ログインユーザ (email).
    password : str
        ログインパスワード.
    """

    site: str
    spider_type: str
    user: str
    password: str


def load_accounts(yaml_path: str | Path) -> dict[str, list[Account]]:
    """``config/accounts.yaml`` を読み込み site→accounts の dict を返す.

    Parameters
    ----------
    yaml_path : str or Path
        YAML ファイルのパス.

    Returns
    -------
    dict[str, list[Account]]
        site 名 → そのサイトのアカウント一覧.

    Raises
    ------
    FileNotFoundError
        YAML ファイルが存在しない場合.
    KeyError
        YAML 内の site キーが ``VARIANTS`` に存在しない場合.
    ValueError
        ``user`` / ``pass`` キーが欠損している、または値が空の場合.
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"accounts yaml not found: {path}")

    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    if not isinstance(raw, dict):
        raise ValueError(
            f"accounts yaml root must be a mapping, got {type(raw).__name__}"
        )

    result: dict[str, list[Account]] = {}
    for site, entries in raw.items():
        if site not in VARIANTS:
            raise KeyError(
                f"unknown site in accounts yaml: {site!r}; known={sorted(VARIANTS)}"
            )
        if not isinstance(entries, list):
            raise ValueError(
                f"site {site!r} must contain a list of accounts, got {type(entries).__name__}"
            )
        accounts: list[Account] = []
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"site {site!r} entry #{idx + 1} must be a mapping")
            user = entry.get("user")
            password = entry.get("pass")
            if not user:
                raise ValueError(
                    f"site {site!r} entry #{idx + 1}: missing or empty 'user'"
                )
            if not password:
                raise ValueError(
                    f"site {site!r} entry #{idx + 1}: missing or empty 'pass'"
                )
            accounts.append(Account(user=str(user), password=str(password)))
        if accounts:
            result[site] = accounts
    return result


def list_invocations(
    accounts_by_site: dict[str, list[Account]],
    *,
    site_filter: str | None = None,
    type_filter: str | None = None,
) -> list[Invocation]:
    """site/account/spider_type を組み合わせて起動予定一覧を生成する.

    Parameters
    ----------
    accounts_by_site : dict[str, list[Account]]
        ``load_accounts`` の戻り値.
    site_filter : str, optional
        指定すれば該当 site のみ.
    type_filter : str, optional
        指定すれば該当 spider 種別のみ (``"transaction"`` 等).

    Returns
    -------
    list[Invocation]
        起動予定一覧. 順序は accounts_by_site の挿入順 × spider_type 列挙順.
    """
    if site_filter is not None and site_filter not in VARIANTS:
        raise KeyError(f"unknown site filter: {site_filter!r}")
    if type_filter is not None and type_filter not in SPIDER_TYPES:
        raise KeyError(f"unknown type filter: {type_filter!r}")

    types = (type_filter,) if type_filter else SPIDER_TYPES
    invocations: list[Invocation] = []
    for site, accounts in accounts_by_site.items():
        if site_filter and site != site_filter:
            continue
        for account in accounts:
            for spider_type in types:
                invocations.append(
                    Invocation(
                        site=site,
                        spider_type=spider_type,
                        user=account.user,
                        password=account.password,
                    )
                )
    return invocations


def _target_spider_types(spider_types: Iterable[str] | None = None) -> tuple[str, ...]:
    """Return validated spider types to touch for output file operations."""
    if spider_types is None:
        return SPIDER_TYPES

    targets = tuple(dict.fromkeys(spider_types))
    unknown = sorted(set(targets) - set(SPIDER_TYPES))
    if unknown:
        raise KeyError(f"unknown spider type(s): {unknown!r}")
    return targets


def initialize_output_files(
    output_dir: Path, spider_types: Iterable[str] | None = None
) -> dict[str, Path]:
    """対象ファイルを ``[`` で初期化 (truncate). run_all 開始前に呼ぶ.

    Parameters
    ----------
    output_dir : Path
        出力ディレクトリ. 存在しなければ作成する.
    spider_types : iterable of str, optional
        初期化対象の spider 種別. 省略時は従来通り 3 種別すべて.

    Returns
    -------
    dict[str, Path]
        spider_type → 初期化後のファイルパス.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for spider_type in _target_spider_types(spider_types):
        path = output_dir / OUTPUT_FILENAME_TEMPLATE.format(spider_type=spider_type)
        path.write_text("[", encoding="utf-8")
        paths[spider_type] = path
    return paths


def finalize_output_files(
    output_dir: Path, spider_types: Iterable[str] | None = None
) -> None:
    """対象ファイルに ``]`` を追記して JSON 配列として valid にする.

    Parameters
    ----------
    output_dir : Path
        出力ディレクトリ.
    spider_types : iterable of str, optional
        finalize 対象の spider 種別. 省略時は従来通り 3 種別すべて.
    """
    for spider_type in _target_spider_types(spider_types):
        path = output_dir / OUTPUT_FILENAME_TEMPLATE.format(spider_type=spider_type)
        if not path.exists():
            continue
        with path.open("a", encoding="utf-8") as fh:
            fh.write("]")


def summarize(
    results: dict[Invocation, str],
    elapsed_sec: float,
    invocations: Iterable[Invocation] | None = None,
) -> dict:
    """サマリを構造化 dict で返す (JSON serializable).

    Parameters
    ----------
    results : dict[Invocation, str]
        invocation → status (``"succeeded"`` or ``"failed: ..."``).
    elapsed_sec : float
        run_all の実行秒数.
    invocations : iterable of Invocation, optional
        起動予定の全 invocation. 指定時は未完了 invocation も失敗として集計する.

    Returns
    -------
    dict
        集計結果.
    """
    planned = tuple(invocations) if invocations is not None else tuple(results)
    total = len(planned)
    succeeded = sum(1 for inv in planned if results.get(inv) == "succeeded")
    failed = {
        f"{inv.site}_{inv.spider_type}_{inv.user}": status
        for inv in planned
        if (status := results.get(inv, "failed: NotCompleted")) != "succeeded"
    }
    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "elapsed_sec": round(elapsed_sec, 1),
    }


def exit_code(summary: dict) -> int:
    """サマリから process exit code を返す (0=全成功, 1=1件以上失敗)."""
    return 0 if not summary.get("failed") else 1


def run_all(
    invocations: list[Invocation],
    settings,
    results: dict[Invocation, str],
):
    """各 invocation を順次実行する Twisted deferred chain を返す.

    Notes
    -----
    Twisted/scrapy 依存はこの関数内のローカル import で完結。pytest 側で
    ``run_all`` のテストする際は ``CrawlerRunner.crawl`` を mock する。

    各 invocation 完了後に crawler の stats を読んで session-expiry が
    永続化していたら ``failed: SessionExpired`` を記録する (Opus M2 fix)。
    ``CrawlerRunner`` 構築自体に失敗した場合は全 invocation を
    ``failed: init_<ExcName>`` でマークする (Opus m6 fix)。

    Parameters
    ----------
    invocations : list[Invocation]
        起動予定一覧.
    settings : scrapy.settings.Settings
        Scrapy 設定.
    results : dict[Invocation, str]
        各 invocation の結果を記録する。
        ``succeeded`` / ``failed: ExcName`` / ``failed: SessionExpired`` /
        ``failed: init_<ExcName>``。

    Returns
    -------
    twisted.internet.defer.Deferred
        全 invocation 完了で resolve する deferred.
    """
    from scrapy import signals
    from scrapy.crawler import CrawlerRunner
    from twisted.internet import defer

    @defer.inlineCallbacks
    def _flow():
        try:
            runner = CrawlerRunner(settings)
        except Exception as exc:  # noqa: BLE001
            # Opus m6: CrawlerRunner 構築失敗時は全 invocation を failed 化
            for inv in invocations:
                results[inv] = f"failed: init_{exc.__class__.__name__}"
            return

        # Capture per-invocation stats via spider_closed signal so the post-run
        # classifier can decide succeeded vs failed: SessionExpired even after
        # the Crawler instance is removed from runner.crawlers. Key the dict
        # on the spider_type (Issue #40 spider class attr) rather than
        # spider.name so the lookup stays correct if spider names diverge
        # from spider_type strings later.
        captured_stats: dict[str, dict] = {}

        def _on_spider_closed(spider, reason) -> None:  # noqa: ARG001
            key = getattr(spider, "spider_type", spider.name)
            try:
                captured_stats[key] = dict(spider.crawler.stats.get_stats())
            except Exception:  # noqa: BLE001, S110
                pass

        for inv in invocations:
            try:
                crawler = runner.create_crawler(inv.spider_type)
                crawler.signals.connect(_on_spider_closed, signal=signals.spider_closed)
                yield runner.crawl(
                    crawler,
                    site=inv.site,
                    login_user=inv.user,
                    login_pass=inv.password,
                )
                stats = captured_stats.pop(inv.spider_type, {})
                results[inv] = _classify_result(inv.spider_type, stats)
            except Exception as exc:  # noqa: BLE001
                logger.exception("crawl_runner: %s failed", inv)
                results[inv] = f"failed: {exc.__class__.__name__}"

    return _flow()


def _classify_result(spider_type: str, stats_snapshot: dict) -> str:
    """Inspect captured stats and decide if the run actually succeeded.

    Middleware が ``login_max_retry`` 上限超過時に ``IgnoreRequest`` を
    raise し、spider の ``_parse_after_login`` も login page を残した時点で
    stats counter を bump する。これらが立っていれば ``succeeded`` でなく
    ``failed: SessionExpired`` として記録する (Opus M2 fix)。
    """
    permanent_keys = (
        f"{spider_type}/session/expired_final",
        f"{spider_type}/login/still_on_login",
        f"{spider_type}/login/failed",
    )
    if any(int(stats_snapshot.get(k, 0) or 0) > 0 for k in permanent_keys):
        return "failed: SessionExpired"
    if int(stats_snapshot.get(f"{spider_type}/months_failed", 0) or 0) > 0:
        return "failed: PartialMonthFetch"
    if int(stats_snapshot.get(f"{spider_type}/playwright/errback", 0) or 0) > 0:
        return "failed: PlaywrightError"
    if any(
        key.startswith("downloader/exception_type_count/playwright.")
        and int(value or 0) > 0
        for key, value in stats_snapshot.items()
    ):
        return "failed: PlaywrightError"
    return "succeeded"


# ``time`` is exposed at module level so callers (and tests) can monkeypatch.
__all__ = [
    "Account",
    "Invocation",
    "OUTPUT_FILENAME_TEMPLATE",
    "SPIDER_TYPES",
    "exit_code",
    "finalize_output_files",
    "initialize_output_files",
    "list_invocations",
    "load_accounts",
    "run_all",
    "summarize",
    "time",
]
