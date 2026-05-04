"""secrets パッケージ専用の例外型."""

from __future__ import annotations


class SecretsError(Exception):
    """secrets backend 全体の基底例外."""


class BackendNotConfigured(SecretsError):
    """SECRETS_BACKEND が未設定 / 不正値、または必須環境変数が不足."""


class SecretNotFound(SecretsError):
    """指定 key が backend に存在しない."""


class BwsApiError(SecretsError):
    """Bitwarden Secrets Manager API 呼出失敗."""
