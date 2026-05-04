"""secrets パッケージのユニットテスト (env mode / bitwarden mode mock)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from moneyforward.secrets import resolver
from moneyforward.secrets.exceptions import (
    BackendNotConfigured,
    SecretNotFound,
)


@pytest.fixture(autouse=True)
def reset_resolver():
    """各テスト前後に resolver global 状態をリセット."""
    resolver.reset_for_test()
    yield
    resolver.reset_for_test()


# ---------------------------------------------------------------- bootstrap
class TestBootstrapEnvMode:
    def test_defaults_to_env_when_backend_not_set(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        resolver.bootstrap()
        assert resolver._backend == "env"
        assert resolver._bootstrapped is True

    def test_explicit_env_backend(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "env")
        resolver.bootstrap()
        assert resolver._backend == "env"

    def test_invalid_backend_raises(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "invalid_backend")
        with pytest.raises(BackendNotConfigured, match="must be one of"):
            resolver.bootstrap()

    def test_idempotent(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        resolver.bootstrap()
        resolver.bootstrap()  # 2回目は no-op
        assert resolver._bootstrapped is True


class TestBootstrapBitwardenMode:
    def test_missing_bws_token_raises(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
        monkeypatch.delenv("BWS_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("ORGANIZATION_ID", raising=False)
        with pytest.raises(BackendNotConfigured, match="必須環境変数"):
            resolver.bootstrap()

    def test_missing_org_id_raises(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
        monkeypatch.setenv("BWS_ACCESS_TOKEN", "dummy_token")
        monkeypatch.delenv("ORGANIZATION_ID", raising=False)
        with pytest.raises(BackendNotConfigured, match="必須環境変数"):
            resolver.bootstrap()

    def test_missing_accounts_secret_raises(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
        monkeypatch.setenv("BWS_ACCESS_TOKEN", "dummy_token")
        monkeypatch.setenv("ORGANIZATION_ID", "dummy_org")

        with patch(
            "moneyforward.secrets.bws_provider.build_client", return_value=MagicMock()
        ):
            with patch(
                "moneyforward.secrets.bws_provider.fetch_normal_secrets",
                return_value={},
            ):
                with pytest.raises(BackendNotConfigured, match="必須 secret が不足"):
                    resolver.bootstrap()

    def test_successful_bootstrap_caches_secrets(self, monkeypatch):
        monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
        monkeypatch.setenv("BWS_ACCESS_TOKEN", "dummy_token")
        monkeypatch.setenv("ORGANIZATION_ID", "dummy_org")
        accounts_json = json.dumps({"mf": [{"user": "u@example.com", "pass": "p"}]})
        cache = {
            "ACCOUNTS": accounts_json,
            "SLACK_INCOMING_WEBHOOK_URL": "https://hooks.slack.com/x",
        }

        with patch(
            "moneyforward.secrets.bws_provider.build_client", return_value=MagicMock()
        ):
            with patch(
                "moneyforward.secrets.bws_provider.fetch_normal_secrets",
                return_value=cache,
            ):
                resolver.bootstrap()

        assert resolver._bootstrapped is True
        assert resolver._backend == "bitwarden"
        assert "ACCOUNTS" in resolver._cache
        assert "SLACK_INCOMING_WEBHOOK_URL" in resolver._cache


# ---------------------------------------------------------------- get
class TestGetEnvMode:
    def test_returns_env_var(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        monkeypatch.setenv("SLACK_INCOMING_WEBHOOK_URL", "https://hooks.slack.com/x")
        assert resolver.get("SLACK_INCOMING_WEBHOOK_URL") == "https://hooks.slack.com/x"

    def test_missing_key_raises_secret_not_found(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        monkeypatch.delenv("SOME_KEY", raising=False)
        with pytest.raises(SecretNotFound, match="env mode"):
            resolver.get("SOME_KEY")

    def test_empty_string_raises_secret_not_found(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        monkeypatch.setenv("SOME_KEY", "")
        with pytest.raises(SecretNotFound):
            resolver.get("SOME_KEY")

    def test_auto_bootstrap_if_not_bootstrapped(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        monkeypatch.setenv("MY_KEY", "my_value")
        assert not resolver._bootstrapped
        result = resolver.get("MY_KEY")
        assert result == "my_value"
        assert resolver._bootstrapped


class TestGetBitwardenMode:
    def _bootstrap_with_cache(self, monkeypatch, cache: dict):
        monkeypatch.setenv("SECRETS_BACKEND", "bitwarden")
        monkeypatch.setenv("BWS_ACCESS_TOKEN", "dummy")
        monkeypatch.setenv("ORGANIZATION_ID", "dummy_org")
        with patch(
            "moneyforward.secrets.bws_provider.build_client", return_value=MagicMock()
        ):
            with patch(
                "moneyforward.secrets.bws_provider.fetch_normal_secrets",
                return_value=cache,
            ):
                resolver.bootstrap()

    def test_returns_cached_value(self, monkeypatch):
        accounts_json = json.dumps({"mf": [{"user": "u@e.com", "pass": "p"}]})
        self._bootstrap_with_cache(monkeypatch, {"ACCOUNTS": accounts_json})
        result = resolver.get("ACCOUNTS")
        assert result == accounts_json

    def test_missing_key_raises_secret_not_found(self, monkeypatch):
        accounts_json = json.dumps({"mf": [{"user": "u@e.com", "pass": "p"}]})
        self._bootstrap_with_cache(monkeypatch, {"ACCOUNTS": accounts_json})
        with pytest.raises(SecretNotFound, match="bitwarden mode"):
            resolver.get("NONEXISTENT_KEY")


# ---------------------------------------------------------------- reset_for_test
class TestResetForTest:
    def test_clears_all_state(self, monkeypatch):
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
        resolver.bootstrap()
        assert resolver._bootstrapped

        resolver.reset_for_test()
        assert not resolver._bootstrapped
        assert resolver._backend is None
        assert resolver._cache == {}
        assert resolver._bws_client is None
