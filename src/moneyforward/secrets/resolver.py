"""dual mode (env / bitwarden) で secrets を解決する単一窓口.

アプリ層は ``resolver.get("ACCOUNTS")`` で値を取得する。
``SECRETS_BACKEND`` 環境変数で経路が切り替わる:

- ``env`` (デフォルト): ``os.environ`` から直接取得 (開発標準・既存挙動互換)
- ``bitwarden``: bootstrap 時に BWS から ``MONEYFORWARD_*`` を一括取得しメモリに保持

bootstrap は idempotent。複数経路から呼ばれても 1 回しか実体動作しない。

smbcnikko_pk からの改変点:
- SECRETS_BACKEND 未設定は "env" fallback (smbcnikko は fail-loud)
- REQUIRED_KEYS = ("ACCOUNTS",) のみ (Slack は optional)
- AUTH_PREFIX 機構 (WebAuthn passkey) は実装しない
- _bootstrap_env は no-op (ACCOUNTS は YAML から取得するため env var チェック不要)
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from moneyforward.secrets.exceptions import (
    BackendNotConfigured,
    SecretNotFound,
)

logger = logging.getLogger(__name__)

_VALID_BACKENDS = ("env", "bitwarden")

#: bitwarden mode で bootstrap 時に必須となる key (app 層の名前)。
REQUIRED_KEYS = ("ACCOUNTS",)

#: bitwarden mode 用必須環境変数 (BWS 接続情報)。
_BWS_REQUIRED_ENV = ("BWS_ACCESS_TOKEN", "ORGANIZATION_ID")

_lock = threading.Lock()
_bootstrapped = False
_backend: str | None = None
_cache: dict[str, str] = {}
_bws_client: Any = None


def _resolve_backend() -> str:
    backend = os.environ.get("SECRETS_BACKEND", "env").strip()
    if backend not in _VALID_BACKENDS:
        raise BackendNotConfigured(
            f"SECRETS_BACKEND must be one of {_VALID_BACKENDS}, got: {backend!r}"
        )
    return backend


def _validate_bws_env() -> None:
    missing = [name for name in _BWS_REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise BackendNotConfigured(f"必須環境変数が不足: {missing}")


def _bootstrap_env() -> None:
    # env mode: ACCOUNTS は YAML から取得するため環境変数チェック不要。
    pass


def _bootstrap_bitwarden() -> None:
    global _cache, _bws_client

    _validate_bws_env()

    from moneyforward.secrets import bws_provider

    client = bws_provider.build_client()
    org_id = os.environ["ORGANIZATION_ID"]
    secrets_map = bws_provider.fetch_normal_secrets(client, org_id)

    missing = [k for k in REQUIRED_KEYS if k not in secrets_map]
    if missing:
        raise BackendNotConfigured(
            f"BWS に必須 secret が不足: {missing} (MONEYFORWARD_<key> として登録要)"
        )

    _cache = secrets_map
    _bws_client = client


def bootstrap() -> None:
    """Secrets backend を初期化 (idempotent).

    複数経路から呼ばれても 1 回しか実体動作しない。失敗時は fail loud で起動拒否。
    """
    global _bootstrapped, _backend

    with _lock:
        if _bootstrapped:
            return
        _backend = _resolve_backend()
        if _backend == "env":
            _bootstrap_env()
        else:
            _bootstrap_bitwarden()
        _bootstrapped = True
        if _backend == "env":
            logger.info(
                "secrets backend initialized: env (no cache; reads from os.environ)"
            )
        else:
            logger.info(
                "secrets backend initialized: bitwarden (cache=%d secrets)", len(_cache)
            )


def get(key: str) -> str:
    """Secret 値を取得する。bootstrap 未実施なら自動的に呼ぶ.

    Parameters
    ----------
    key : str
        アプリ層の key (例: ``"ACCOUNTS"``)。BWS 上の prefix は意識しない。

    Returns
    -------
    str
        secret 値。

    Raises
    ------
    SecretNotFound
        env mode で ``os.environ`` に該当キーがない / 空、または bitwarden mode の
        cache に該当キーが含まれていない場合。
    """
    if not _bootstrapped:
        bootstrap()

    if _backend == "env":
        value = os.environ.get(key)
        if not value:
            raise SecretNotFound(f"env mode: {key} が os.environ に存在しない")
        return value

    value = _cache.get(key)
    if not value:
        raise SecretNotFound(f"bitwarden mode: {key} が BWS から取得できなかった")
    return value


def reset_for_test() -> None:
    """テスト専用。global 状態を初期化する。プロダクションコードからは呼ばない."""
    global _bootstrapped, _backend, _cache, _bws_client
    with _lock:
        _bootstrapped = False
        _backend = None
        _cache = {}
        _bws_client = None
