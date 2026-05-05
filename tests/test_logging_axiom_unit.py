"""logging_config の Axiom ハンドラ ユニットテスト"""

from __future__ import annotations

import logging
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import moneyforward.utils.logging_config as _logging_mod
from moneyforward.utils.logging_config import (
    _CONFIGURED_FLAG,
    _build_axiom_handler,
    _get_axiom_handler,
    setup_common_logging,
)


@pytest.fixture(autouse=True)
def _clear_axiom_env(monkeypatch):
    monkeypatch.delenv("AXIOM_TOKEN", raising=False)
    monkeypatch.delenv("AXIOM_ORG_ID", raising=False)
    monkeypatch.delenv("AXIOM_DATASET", raising=False)


@pytest.fixture(autouse=True)
def _reset_axiom_singleton():
    original = _logging_mod._axiom_handler
    _logging_mod._axiom_handler = _logging_mod._UNSET
    yield
    _logging_mod._axiom_handler = original


@pytest.fixture()
def _reset_root_logging():
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_flag = getattr(root, _CONFIGURED_FLAG, False)
    setattr(root, _CONFIGURED_FLAG, False)
    yield
    root.handlers = original_handlers
    setattr(root, _CONFIGURED_FLAG, original_flag)


@pytest.fixture()
def fake_axiom():
    """axiom_py / axiom_py.logging をフェイクモジュールとして sys.modules に注入。"""
    client_cls = MagicMock()
    mock_handler_instance = MagicMock(spec=logging.Handler)
    mock_handler_instance.filters = []
    handler_cls = MagicMock(return_value=mock_handler_instance)

    mod = types.ModuleType("axiom_py")
    mod.Client = client_cls  # type: ignore[attr-defined]

    log_mod = types.ModuleType("axiom_py.logging")
    log_mod.AxiomHandler = handler_cls  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"axiom_py": mod, "axiom_py.logging": log_mod}):
        yield client_cls, handler_cls


class TestBuildAxiomHandler:
    def test_returns_none_when_no_env(self):
        assert _build_axiom_handler() is None

    def test_returns_none_when_only_token(self, monkeypatch):
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        assert _build_axiom_handler() is None

    def test_returns_none_when_only_org_id(self, monkeypatch):
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        assert _build_axiom_handler() is None

    def test_returns_none_on_whitespace_token(self, monkeypatch):
        monkeypatch.setenv("AXIOM_TOKEN", "   ")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        assert _build_axiom_handler() is None

    def test_returns_handler_when_both_set(self, monkeypatch, fake_axiom):
        mock_client_cls, mock_handler_cls = fake_axiom
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        result = _build_axiom_handler()
        mock_client_cls.assert_called_once_with(token="xaat-test", org_id="my-org")  # noqa: S106
        assert result is mock_handler_cls.return_value

    def test_strips_whitespace_from_token_and_org_id(self, monkeypatch, fake_axiom):
        mock_client_cls, _ = fake_axiom
        monkeypatch.setenv("AXIOM_TOKEN", "  xaat-test  ")
        monkeypatch.setenv("AXIOM_ORG_ID", "  my-org  ")
        _build_axiom_handler()
        mock_client_cls.assert_called_once_with(token="xaat-test", org_id="my-org")  # noqa: S106

    def test_default_dataset(self, monkeypatch, fake_axiom):
        mock_client_cls, mock_handler_cls = fake_axiom
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        _build_axiom_handler()
        mock_handler_cls.assert_called_once_with(
            client=mock_client_cls.return_value, dataset="moneyforward-crawler"
        )

    def test_custom_dataset(self, monkeypatch, fake_axiom):
        mock_client_cls, mock_handler_cls = fake_axiom
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        monkeypatch.setenv("AXIOM_DATASET", "custom-ds")
        _build_axiom_handler()
        mock_handler_cls.assert_called_once_with(
            client=mock_client_cls.return_value, dataset="custom-ds"
        )

    def test_handler_level_set_to_info(self, monkeypatch, fake_axiom):
        _, mock_handler_cls = fake_axiom
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        _build_axiom_handler()
        mock_handler_cls.return_value.setLevel.assert_called_once_with(logging.INFO)

    def test_returns_none_on_import_error(self, monkeypatch):
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        with patch.dict(sys.modules, {"axiom_py": None}):
            result = _build_axiom_handler()
        assert result is None

    def test_returns_none_on_client_exception(self, monkeypatch, fake_axiom, capsys):
        mock_client_cls, _ = fake_axiom
        mock_client_cls.side_effect = RuntimeError("network error")
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        result = _build_axiom_handler()
        assert result is None
        assert "[axiom]" in capsys.readouterr().err

    def test_returns_none_on_handler_exception(self, monkeypatch, fake_axiom, capsys):
        _, mock_handler_cls = fake_axiom
        mock_handler_cls.side_effect = RuntimeError("ax fail")
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        result = _build_axiom_handler()
        assert result is None
        assert "[axiom]" in capsys.readouterr().err


class TestGetAxiomHandlerSingleton:
    def test_singleton_returns_same_instance(self, monkeypatch, fake_axiom):
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        h1 = _get_axiom_handler()
        h2 = _get_axiom_handler()
        assert h1 is h2

    def test_singleton_calls_build_only_once(self, monkeypatch, fake_axiom):
        _, mock_handler_cls = fake_axiom
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        _get_axiom_handler()
        _get_axiom_handler()
        assert mock_handler_cls.call_count == 1


class TestSetupCommonLoggingAxiomIntegration:
    def test_no_axiom_handler_when_env_missing(self, _reset_root_logging):
        setup_common_logging()
        root = logging.getLogger()
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "AxiomHandler" not in handler_types

    def test_axiom_handler_added_when_env_set(
        self, monkeypatch, fake_axiom, _reset_root_logging
    ):
        _, mock_handler_cls = fake_axiom
        monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
        monkeypatch.setenv("AXIOM_ORG_ID", "my-org")
        setup_common_logging()
        assert mock_handler_cls.return_value in logging.getLogger().handlers
