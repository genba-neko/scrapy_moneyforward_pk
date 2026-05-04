"""Unit tests for crawl_runner core (reactor 非依存部分)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from moneyforward._runner_core import (
    SPIDER_TYPES,
    Account,
    Invocation,
    _classify_result,
    exit_code,
    finalize_output_files,
    initialize_output_files,
    list_invocations,
    load_accounts,
    summarize,
)

# --------------------------------------------------------------------- helpers


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "accounts.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


# ---------------------------------------------------------------- load_accounts


def test_load_accounts_basic(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
        mf:
          - user: a@example.com
            pass: pwd1
          - user: b@example.com
            pass: pwd2
        xmf_ssnb:
          - user: c@example.com
            pass: pwd3
        """,
    )
    result = load_accounts(path)
    assert result == {
        "mf": [
            Account(user="a@example.com", password="pwd1"),
            Account(user="b@example.com", password="pwd2"),
        ],
        "xmf_ssnb": [Account(user="c@example.com", password="pwd3")],
    }


def test_load_accounts_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_accounts(tmp_path / "nope.yaml")


def test_load_accounts_unknown_site(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
        ghost_bank:
          - user: a@example.com
            pass: pwd1
        """,
    )
    with pytest.raises(KeyError, match="unknown site"):
        load_accounts(path)


def test_load_accounts_missing_pass(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
        mf:
          - user: a@example.com
        """,
    )
    with pytest.raises(ValueError, match="missing or empty 'pass'"):
        load_accounts(path)


def test_load_accounts_missing_user(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
        mf:
          - pass: pwd1
        """,
    )
    with pytest.raises(ValueError, match="missing or empty 'user'"):
        load_accounts(path)


def test_load_accounts_empty_yaml(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, "")
    assert load_accounts(path) == {}


def test_load_accounts_root_not_mapping(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, "- a\n- b\n")
    with pytest.raises(ValueError, match="root must be a mapping"):
        load_accounts(path)


def test_load_accounts_skips_empty_account_list(tmp_path: Path) -> None:
    path = _write_yaml(
        tmp_path,
        """
        mf: []
        """,
    )
    assert load_accounts(path) == {}


def test_load_accounts_env_mode_requires_yaml_path() -> None:
    # SECRETS_BACKEND 未設定 = env mode → yaml_path=None は ValueError
    with pytest.raises(ValueError, match="yaml_path"):
        load_accounts(None)


# -------------------------------------------------------- bitwarden mode


def test_load_accounts_bitwarden_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
    accounts_json = json.dumps({"mf": [{"user": "u@example.com", "pass": "secret"}]})
    with patch("moneyforward.secrets.resolver.get", return_value=accounts_json):
        result = load_accounts()
    assert result == {"mf": [Account(user="u@example.com", password="secret")]}


def test_load_accounts_bitwarden_ignores_yaml_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
    accounts_json = json.dumps({"mf": [{"user": "u@example.com", "pass": "p"}]})
    with patch("moneyforward.secrets.resolver.get", return_value=accounts_json):
        result = load_accounts(tmp_path / "nonexistent.yaml")
    assert "mf" in result


def test_load_accounts_bitwarden_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
    with patch("moneyforward.secrets.resolver.get", return_value="not-json"):
        with pytest.raises(ValueError, match="JSON パース失敗"):
            load_accounts()


def test_load_accounts_bitwarden_unknown_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
    accounts_json = json.dumps({"ghost_bank": [{"user": "u@example.com", "pass": "p"}]})
    with patch("moneyforward.secrets.resolver.get", return_value=accounts_json):
        with pytest.raises(KeyError, match="unknown site"):
            load_accounts()


def test_load_accounts_bitwarden_missing_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
    accounts_json = json.dumps({"mf": [{"user": "u@example.com"}]})
    with patch("moneyforward.secrets.resolver.get", return_value=accounts_json):
        with pytest.raises(ValueError, match="missing or empty 'pass'"):
            load_accounts()


# ------------------------------------------------------------- list_invocations


@pytest.fixture
def sample_accounts() -> dict[str, list[Account]]:
    return {
        "mf": [
            Account(user="a@x.com", password="p1"),
            Account(user="b@x.com", password="p2"),
        ],
        "xmf_ssnb": [Account(user="c@y.com", password="p3")],
    }


def test_list_invocations_full(sample_accounts: dict[str, list[Account]]) -> None:
    invs = list_invocations(sample_accounts)
    # 3 accounts × 3 spider types = 9
    assert len(invs) == 9
    sites = {i.site for i in invs}
    types = {i.spider_type for i in invs}
    assert sites == {"mf", "xmf_ssnb"}
    assert types == set(SPIDER_TYPES)


def test_list_invocations_site_filter(
    sample_accounts: dict[str, list[Account]],
) -> None:
    invs = list_invocations(sample_accounts, site_filter="xmf_ssnb")
    # 1 account × 3 types
    assert len(invs) == 3
    assert all(i.site == "xmf_ssnb" for i in invs)


def test_list_invocations_type_filter(
    sample_accounts: dict[str, list[Account]],
) -> None:
    invs = list_invocations(sample_accounts, type_filter="transaction")
    # 3 accounts × 1 type
    assert len(invs) == 3
    assert all(i.spider_type == "transaction" for i in invs)


def test_list_invocations_both_filters(
    sample_accounts: dict[str, list[Account]],
) -> None:
    invs = list_invocations(sample_accounts, site_filter="mf", type_filter="account")
    # 2 mf accounts × 1 type
    assert len(invs) == 2
    assert {i.user for i in invs} == {"a@x.com", "b@x.com"}
    assert all(i.spider_type == "account" for i in invs)


def test_list_invocations_unknown_site_filter(
    sample_accounts: dict[str, list[Account]],
) -> None:
    with pytest.raises(KeyError, match="unknown site filter"):
        list_invocations(sample_accounts, site_filter="ghost")


def test_list_invocations_unknown_type_filter(
    sample_accounts: dict[str, list[Account]],
) -> None:
    with pytest.raises(KeyError, match="unknown type filter"):
        list_invocations(sample_accounts, type_filter="balance")


def test_invocation_carries_account_credentials(
    sample_accounts: dict[str, list[Account]],
) -> None:
    invs = list_invocations(
        sample_accounts, site_filter="mf", type_filter="transaction"
    )
    assert invs[0] == Invocation(
        site="mf",
        spider_type="transaction",
        user="a@x.com",
        password="p1",
    )
    assert invs[1].user == "b@x.com"


# --------------------------------------------------------- output file helpers


def test_initialize_output_files_creates_three_files(tmp_path: Path) -> None:
    paths = initialize_output_files(tmp_path)
    assert set(paths) == set(SPIDER_TYPES)
    for st, p in paths.items():
        assert p.exists()
        assert p.read_text(encoding="utf-8") == "["
        assert p.name == f"moneyforward_{st}.json"


def test_initialize_output_files_truncates_existing(tmp_path: Path) -> None:
    pre = tmp_path / "moneyforward_transaction.json"
    pre.write_text('[{"x": 1}]', encoding="utf-8")
    initialize_output_files(tmp_path)
    assert pre.read_text(encoding="utf-8") == "["


def test_initialize_output_files_only_touches_requested_types(tmp_path: Path) -> None:
    transaction = tmp_path / "moneyforward_transaction.json"
    account = tmp_path / "moneyforward_account.json"
    asset = tmp_path / "moneyforward_asset_allocation.json"
    transaction.write_text('[{"keep": "transaction"}]', encoding="utf-8")
    account.write_text('[{"old": "account"}]', encoding="utf-8")
    asset.write_text('[{"keep": "asset"}]', encoding="utf-8")

    paths = initialize_output_files(tmp_path, ("account",))

    assert set(paths) == {"account"}
    assert transaction.read_text(encoding="utf-8") == '[{"keep": "transaction"}]'
    assert account.read_text(encoding="utf-8") == "["
    assert asset.read_text(encoding="utf-8") == '[{"keep": "asset"}]'


def test_finalize_output_files_appends_closing_bracket(tmp_path: Path) -> None:
    initialize_output_files(tmp_path)
    finalize_output_files(tmp_path)
    for st in SPIDER_TYPES:
        p = tmp_path / f"moneyforward_{st}.json"
        text = p.read_text(encoding="utf-8")
        # Empty array but valid JSON (pretty-printed: "[\n]")
        assert json.loads(text) == []


def test_finalize_output_files_with_items_is_valid_json(tmp_path: Path) -> None:
    initialize_output_files(tmp_path)
    p = tmp_path / "moneyforward_transaction.json"
    # Simulate two pipeline writes
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"a": 1}')
        fh.write(',{"b": 2}')
    finalize_output_files(tmp_path)
    text = p.read_text(encoding="utf-8")
    assert json.loads(text) == [{"a": 1}, {"b": 2}]


def test_finalize_output_files_only_touches_requested_types(tmp_path: Path) -> None:
    transaction = tmp_path / "moneyforward_transaction.json"
    account = tmp_path / "moneyforward_account.json"
    asset = tmp_path / "moneyforward_asset_allocation.json"
    transaction.write_text('[{"keep": "transaction"}]', encoding="utf-8")
    account.write_text('[{"new": "account"}', encoding="utf-8")
    asset.write_text('[{"keep": "asset"}]', encoding="utf-8")

    finalize_output_files(tmp_path, ("account",))

    assert transaction.read_text(encoding="utf-8") == '[{"keep": "transaction"}]'
    assert json.loads(account.read_text(encoding="utf-8")) == [{"new": "account"}]
    assert asset.read_text(encoding="utf-8") == '[{"keep": "asset"}]'


# --------------------------------------------------------------- summarize


def _inv(site: str, spider_type: str, user: str) -> Invocation:
    return Invocation(site=site, spider_type=spider_type, user=user, password="x")


def test_summarize_all_succeeded() -> None:
    results = {
        _inv("mf", "transaction", "a@x.com"): "succeeded",
        _inv("mf", "account", "a@x.com"): "succeeded",
    }
    s = summarize(results, elapsed_sec=12.3)
    assert s["total"] == 2
    assert s["succeeded"] == 2
    assert s["failed"] == {}
    assert s["elapsed_sec"] == 12.3


def test_summarize_mixed() -> None:
    results = {
        _inv("mf", "transaction", "a@x.com"): "succeeded",
        _inv("xmf_ssnb", "transaction", "c@y.com"): "failed: HttpError",
    }
    s = summarize(results, elapsed_sec=5.0)
    assert s["succeeded"] == 1
    assert "xmf_ssnb_transaction_c@y.com" in s["failed"]
    assert s["failed"]["xmf_ssnb_transaction_c@y.com"] == "failed: HttpError"


def test_summarize_is_json_serializable() -> None:
    results = {_inv("mf", "transaction", "a@x.com"): "succeeded"}
    s = summarize(results, elapsed_sec=1.0)
    # Should round-trip via json without TypeError
    json.dumps(s)


def test_summarize_marks_missing_planned_invocations_failed() -> None:
    finished = _inv("mf", "transaction", "a@x.com")
    pending = _inv("mf", "account", "a@x.com")

    s = summarize(
        {finished: "succeeded"},
        elapsed_sec=12.3,
        invocations=[finished, pending],
    )

    assert s["total"] == 2
    assert s["succeeded"] == 1
    assert s["failed"] == {
        "mf_account_a@x.com": "failed: NotCompleted",
    }


# --------------------------------------------------------------- exit_code


def test_exit_code_zero_when_all_succeeded() -> None:
    assert exit_code({"failed": {}, "total": 5, "succeeded": 5}) == 0


def test_exit_code_one_when_any_failed() -> None:
    assert exit_code({"failed": {"x": "fail"}, "total": 2, "succeeded": 1}) == 1


# ------------------------------------------------------------------- run_all


def _build_fake_runner(stats_by_spider_type=None, fail_spider_types=None):
    """Build a CrawlerRunner mock that fires spider_closed callbacks with stats.

    Each ``runner.create_crawler(spider_type)`` returns a mock crawler whose
    ``signals.connect`` records the handler. ``runner.crawl(crawler, ...)``
    invokes any recorded ``spider_closed`` handler with a fake spider whose
    ``crawler.stats.get_stats()`` returns the per-type dict, then returns
    ``defer.succeed(None)`` (or ``defer.fail(...)`` for ``fail_spider_types``).
    """
    from twisted.internet import defer

    stats_by_spider_type = stats_by_spider_type or {}
    fail_spider_types = fail_spider_types or {}

    fake_runner = MagicMock()

    def _create_crawler(spider_type):
        crawler = MagicMock()
        crawler.spider_type = spider_type
        crawler.handlers = []

        def _connect(handler, signal):  # noqa: ARG001
            crawler.handlers.append(handler)

        crawler.signals.connect.side_effect = _connect
        return crawler

    def _crawl(crawler, **_kwargs):
        spider_type = crawler.spider_type
        # Build a fake spider for the close-signal callback. The hook reads
        # ``spider.spider_type`` (Issue #40), so set it explicitly rather than
        # relying on MagicMock auto-attrs which would coerce to a Mock object.
        fake_spider = MagicMock()
        fake_spider.name = spider_type
        fake_spider.spider_type = spider_type
        fake_spider.crawler.stats.get_stats.return_value = stats_by_spider_type.get(
            spider_type, {}
        )
        for handler in crawler.handlers:
            handler(spider=fake_spider, reason="finished")
        if spider_type in fail_spider_types:
            return defer.fail(fail_spider_types[spider_type])
        return defer.succeed(None)

    fake_runner.create_crawler.side_effect = _create_crawler
    fake_runner.crawl.side_effect = _crawl
    return fake_runner


def test_run_all_continues_after_individual_spider_failure() -> None:
    """A single spider raising must not abort the loop; results recorded."""
    invs = [
        _inv("mf", "transaction", "a@x.com"),
        _inv("mf", "account", "a@x.com"),
        _inv("xmf_ssnb", "transaction", "c@y.com"),
    ]

    fake_runner = _build_fake_runner(
        fail_spider_types={"account": RuntimeError("simulated failure")},
    )

    with patch("scrapy.crawler.CrawlerRunner", return_value=fake_runner):
        from moneyforward._runner_core import run_all

        results: dict = {}
        flow = run_all(invs, settings=MagicMock(), results=results)
        assert flow.called

    assert results[invs[0]] == "succeeded"
    assert results[invs[1]].startswith("failed: ")
    assert "RuntimeError" in results[invs[1]]
    assert results[invs[2]] == "succeeded"
    assert fake_runner.crawl.call_count == 3


def test_run_all_marks_session_expiry_as_failed() -> None:
    """When stats show login/still_on_login or session/expired_final, mark failed."""
    invs = [
        _inv("mf", "transaction", "a@x.com"),
        _inv("mf", "account", "b@x.com"),
        _inv("mf", "asset_allocation", "c@x.com"),
    ]

    stats_by_type = {
        "transaction": {"transaction/login/still_on_login": 1},
        "account": {"account/session/expired_final": 1},
        "asset_allocation": {"asset_allocation/login/failed": 1},
    }
    fake_runner = _build_fake_runner(stats_by_spider_type=stats_by_type)

    with patch("scrapy.crawler.CrawlerRunner", return_value=fake_runner):
        from moneyforward._runner_core import run_all

        results: dict = {}
        flow = run_all(invs, settings=MagicMock(), results=results)
        assert flow.called

    for inv in invs:
        assert results[inv] == "failed: SessionExpired", inv


def test_classify_result_marks_months_failed_as_partial() -> None:
    assert (
        _classify_result("transaction", {"transaction/months_failed": 1})
        == "failed: PartialMonthFetch"
    )


def test_classify_result_marks_playwright_errback_failed() -> None:
    assert (
        _classify_result("transaction", {"transaction/playwright/errback": 1})
        == "failed: PlaywrightError"
    )


def test_classify_result_marks_playwright_downloader_exception_failed() -> None:
    status = _classify_result(
        "transaction",
        {
            "downloader/exception_type_count/playwright._impl._errors.TargetClosedError": 1
        },
    )

    assert status == "failed: PlaywrightError"


def test_run_all_marks_init_failure_for_all_invocations() -> None:
    """Opus m6: CrawlerRunner construction failure marks every invocation."""
    invs = [
        _inv("mf", "transaction", "a@x.com"),
        _inv("xmf_ssnb", "account", "b@y.com"),
    ]

    with patch(
        "scrapy.crawler.CrawlerRunner",
        side_effect=RuntimeError("settings broken"),
    ):
        from moneyforward._runner_core import run_all

        results: dict = {}
        flow = run_all(invs, settings=MagicMock(), results=results)
        assert flow.called

    for inv in invs:
        assert results[inv].startswith("failed: init_RuntimeError"), inv
