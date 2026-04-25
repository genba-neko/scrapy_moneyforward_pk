"""Pytest fixtures. Seeds dummy env vars before settings.py import."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("LOG_FILE_ENABLED", "false")
os.environ.setdefault("SITE_LOGIN_USER", "test@example.com")
os.environ.setdefault("SITE_LOGIN_PASS", "dummy-password")
os.environ.setdefault("SITE_PAST_MONTHS", "2")
os.environ.setdefault("MONEYFORWARD_HEADLESS", "true")

# Make src/ importable when tests run without pytest's pythonpath config (e.g. ruff imports).
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


@pytest.fixture
def fake_stats():
    from tests.helpers import FakeStats

    return FakeStats()
