"""Unit tests for SessionManager (Playwright storage_state persistence)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from moneyforward_pk.auth import SessionManager
from moneyforward_pk.auth.session_manager import _hash_user


def _run(coro):
    """Drive a coroutine synchronously without pytest-asyncio."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_state_path_is_per_site_per_user(tmp_path: Path):
    sm_a = SessionManager(tmp_path, site="mf", login_user="a@x.com")
    sm_b = SessionManager(tmp_path, site="mf", login_user="b@x.com")
    sm_c = SessionManager(tmp_path, site="xmf_ssnb", login_user="a@x.com")
    assert sm_a.state_path != sm_b.state_path
    assert sm_a.state_path != sm_c.state_path
    assert sm_a.state_path.parent == tmp_path
    assert sm_a.state_path.name.startswith("mf_")
    assert sm_a.state_path.suffix == ".json"


def test_state_path_does_not_leak_email(tmp_path: Path):
    sm = SessionManager(tmp_path, site="mf", login_user="alice@example.com")
    name = sm.state_path.name
    assert "alice" not in name
    assert "example" not in name
    assert _hash_user("alice@example.com") in name


def test_has_saved_session_false_when_missing(tmp_path: Path):
    sm = SessionManager(tmp_path, site="mf", login_user="a@x.com")
    assert sm.has_saved_session() is False
    assert sm.get_storage_state() is None


def test_has_saved_session_true_when_file_present(tmp_path: Path):
    sm = SessionManager(tmp_path, site="mf", login_user="a@x.com")
    sm.state_path.parent.mkdir(parents=True, exist_ok=True)
    sm.state_path.write_text("{}", encoding="utf-8")
    assert sm.has_saved_session() is True
    assert sm.get_storage_state() == str(sm.state_path)


def test_has_saved_session_false_when_empty_file(tmp_path: Path):
    sm = SessionManager(tmp_path, site="mf", login_user="a@x.com")
    sm.state_path.parent.mkdir(parents=True, exist_ok=True)
    sm.state_path.write_text("", encoding="utf-8")
    assert sm.has_saved_session() is False


def test_invalidate_session_removes_existing_file(tmp_path: Path):
    sm = SessionManager(tmp_path, site="mf", login_user="a@x.com")
    sm.state_path.parent.mkdir(parents=True, exist_ok=True)
    sm.state_path.write_text("{}", encoding="utf-8")
    sm.invalidate_session()
    assert not sm.state_path.exists()


def test_invalidate_session_no_op_when_missing(tmp_path: Path):
    sm = SessionManager(tmp_path, site="mf", login_user="a@x.com")
    # Must not raise even when the state has never been written.
    sm.invalidate_session()


def test_save_from_context_invokes_storage_state(tmp_path: Path):
    sm = SessionManager(tmp_path / "deep", site="mf", login_user="a@x.com")
    fake_context = MagicMock()
    fake_context.storage_state = AsyncMock()
    _run(sm.save_from_context(fake_context))
    fake_context.storage_state.assert_awaited_once_with(path=str(sm.state_path))
    # Directory must be created lazily.
    assert sm.state_path.parent.is_dir()


def test_save_from_context_swallows_failures(tmp_path: Path):
    """A failed storage_state save must not abort the spider."""
    sm = SessionManager(tmp_path, site="mf", login_user="a@x.com")
    fake_context = MagicMock()
    fake_context.storage_state = AsyncMock(side_effect=RuntimeError("disk full"))
    # Must not raise.
    _run(sm.save_from_context(fake_context))
