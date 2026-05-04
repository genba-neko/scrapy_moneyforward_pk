"""Multi-site/account/type crawl orchestrator.

Reads ``config/accounts.yaml`` and runs the configured (site, account,
spider_type) tuples sequentially via Scrapy's ``CrawlerRunner``. Each
spider invocation appends to one of three aggregated JSON-array files
(``moneyforward_transaction.json`` / ``_account.json`` /
``_asset_allocation.json``) under ``runtime/output/``.

Usage
-----
::

    cd src
    python -m moneyforward.crawl_runner
    python -m moneyforward.crawl_runner --type transaction
    python -m moneyforward.crawl_runner --site xmf_ssnb
    python -m moneyforward.crawl_runner --list

The ``site`` / ``type`` filters are AND-combined.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Build CLI arguments for crawl_runner."""
    parser = argparse.ArgumentParser(
        prog="moneyforward.crawl_runner",
        description="Run all configured (site, account, spider_type) crawls sequentially.",
    )
    parser.add_argument(
        "--site",
        default=None,
        help="Restrict to a single site (e.g. xmf_ssnb).",
    )
    parser.add_argument(
        "--type",
        dest="spider_type",
        default=None,
        choices=("transaction", "account", "asset_allocation"),
        help="Restrict to a single spider type.",
    )
    parser.add_argument(
        "--accounts",
        default=str(Path("..") / "config" / "accounts.yaml"),
        help="Path to accounts YAML (default: <project_root>/config/accounts.yaml).",
    )
    parser.add_argument(
        "--list",
        dest="list_only",
        action="store_true",
        help="Print the planned invocations and exit without running.",
    )
    return parser.parse_args(argv)


def _resolve_accounts_path(raw: str) -> Path:
    """Resolve the accounts YAML path relative to the project root if needed."""
    p = Path(raw)
    if p.is_absolute():
        return p
    project_root = Path(__file__).resolve().parents[2]
    # Common usage: invoked from src/, so the default is "../config/...".
    if p.parts and p.parts[0] == "..":
        return (Path.cwd() / p).resolve()
    return (project_root / p).resolve()


def _print_summary(summary: dict) -> None:
    print("=== Crawl Runner Summary ===")
    print(f"Total invocations:  {summary['total']}")
    print(f"Succeeded:          {summary['succeeded']}")
    failed = summary.get("failed") or {}
    print(f"Failed:             {len(failed)}")
    for label, reason in failed.items():
        print(f"  - {label}: {reason}")
    print(f"Elapsed:            {summary['elapsed_sec']}s")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)

    # Opus M3: preserve the original cwd so calling ``main()`` from a test or
    # parent process does not leak ``src/`` as a permanent cwd.
    original_cwd = Path.cwd()
    src_dir = Path(__file__).resolve().parent.parent
    if Path.cwd() != src_dir:
        os.chdir(src_dir)

    try:
        return _run(args)
    finally:
        os.chdir(original_cwd)


def _run(args: argparse.Namespace) -> int:
    """Inner entry point. Assumes cwd is already ``src/``."""
    # reactor install must happen *before* any scrapy/twisted import that
    # would auto-install the default reactor. Doing it inside main() (not at
    # module import) keeps the reactor singleton untouched for unit tests.
    from scrapy.utils.reactor import install_reactor

    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

    from scrapy.utils.project import get_project_settings
    from twisted.internet import reactor

    from moneyforward._runner_core import (
        exit_code,
        finalize_output_files,
        initialize_output_files,
        list_invocations,
        load_accounts,
        run_all,
        summarize,
    )
    from moneyforward.utils.logging_config import setup_common_logging
    from moneyforward.utils.paths import resolve_output_dir

    setup_common_logging()

    accounts_path = _resolve_accounts_path(args.accounts)
    bitwarden_mode = os.environ.get("SECRETS_BACKEND", "env") == "bitwarden"
    if not bitwarden_mode and not accounts_path.exists():
        logger.error("accounts.yaml not found: %s", accounts_path)
        return 1

    accounts = load_accounts(None if bitwarden_mode else accounts_path)
    invocations = list_invocations(
        accounts,
        site_filter=args.site,
        type_filter=args.spider_type,
    )

    if args.list_only:
        for inv in invocations:
            print(f"{inv.site}\t{inv.spider_type}\t{inv.user}")
        print(f"# total: {len(invocations)}", file=sys.stderr)
        return 0

    if not invocations:
        logger.warning("No invocations configured. Check accounts.yaml.")
        return 0

    settings = get_project_settings()
    default_dir = Path(settings.get("OUTPUT_DIR_DEFAULT", "runtime/output"))
    output_dir = resolve_output_dir(settings.get("OUTPUT_DIR", ""), default_dir)
    target_spider_types = tuple(dict.fromkeys(inv.spider_type for inv in invocations))
    initialize_output_files(output_dir, target_spider_types)

    results: dict = {}
    started_at = time.monotonic()

    # Opus m12: ensure finalize is invoked even if reactor.run() raises so the
    # 3 output files always end with the closing ``]`` (valid JSON array).
    try:
        flow = run_all(invocations, settings, results)
        # Opus M3: schedule reactor.stop via callLater so a flow that already
        # resolved synchronously (e.g. CrawlerRunner init failure) does not
        # call reactor.stop() before reactor.run() has started.
        flow.addBoth(
            lambda _: reactor.callLater(0, reactor.stop)  # type: ignore[attr-defined]
        )
        reactor.run()  # type: ignore[attr-defined]
    finally:
        finalize_output_files(output_dir, target_spider_types)

    elapsed = time.monotonic() - started_at
    summary = summarize(results, elapsed, invocations)
    _print_summary(summary)
    return exit_code(summary)


if __name__ == "__main__":
    sys.exit(main())
