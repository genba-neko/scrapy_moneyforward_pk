"""Pytest fixtures for moneyforward.

Environment isolation: per-test ``monkeypatch.setenv`` is used; module-level
``os.environ.setdefault`` is intentionally avoided so tests cannot leak
developer/CI shell state into the process. T3 / iter1.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make src/ importable when tests run without pytest's pythonpath config (e.g.
# linters that import test modules without configuring pyproject.toml).
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

FIXTURES_DIR = _HERE / "fixtures"

# Env keys that the test fixtures own. autouse cleanup keeps each test
# independent of any inherited shell env.
_OWNED_ENV_KEYS = (
    "LOG_FILE_ENABLED",
    "LOG_FILE_PATH",
    "SITE_LOGIN_USER",
    "SITE_LOGIN_PASS",
    "SITE_LOGIN_ALT_USER",
    "SITE_LOGIN_ALT_PASS",
    "SITE_PAST_MONTHS",
    "MONEYFORWARD_HEADLESS",
    "MONEYFORWARD_LOGIN_MAX_RETRY",
    "OUTPUT_DIR",
    "OUTPUT_FILENAME_TEMPLATE",
    "SLACK_INCOMING_WEBHOOK_URL",
)


@pytest.fixture(autouse=True)
def _isolate_moneyforward_env(monkeypatch):
    """Strip MoneyForward-related env from each test (no setdefault)."""
    for key in _OWNED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def mf_test_env(monkeypatch):
    """Provide a minimal credential-set for tests that exercise login wiring."""
    monkeypatch.setenv("SITE_LOGIN_USER", "test@example.com")
    monkeypatch.setenv("SITE_LOGIN_PASS", "dummy-password")
    monkeypatch.setenv("SITE_PAST_MONTHS", "2")
    monkeypatch.setenv("MONEYFORWARD_HEADLESS", "true")
    monkeypatch.setenv("LOG_FILE_ENABLED", "false")
    return {
        "SITE_LOGIN_USER": "test@example.com",
        "SITE_LOGIN_PASS": "dummy-password",
    }


@pytest.fixture
def fixture_html():
    """Return a callable that loads a fixture HTML file by name."""

    def _load(name: str) -> str:
        path = FIXTURES_DIR / name
        return path.read_text(encoding="utf-8")

    return _load


@pytest.fixture
def fake_stats():
    from tests.helpers import FakeStats

    return FakeStats()
