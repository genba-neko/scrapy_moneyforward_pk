"""Bitwarden Secrets Manager (BWS) クライアント薄ラッパー.

本番経路で使うのは `fetch_normal_secrets`。
list はメタデータのみ返却されるため、値取得には get_by_ids を使う。
AUTH_PREFIX 機構 (WebAuthn passkey) は本PJに不要なため実装しない。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from moneyforward.secrets.exceptions import BwsApiError

if TYPE_CHECKING:
    from bitwarden_sdk import BitwardenClient

DEFAULT_API_URL = "https://api.bitwarden.com"
DEFAULT_IDENTITY_URL = "https://identity.bitwarden.com"

#: BWS 上の key に付与する project prefix。
#: アプリ層は prefix を意識せず resolver.get("ACCOUNTS") で透過アクセスする。
BWS_KEY_PREFIX = "MONEYFORWARD_"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise BwsApiError(f"環境変数未設定: {name}")
    return value


def build_client() -> BitwardenClient:
    """BitwardenClient を初期化して access token でログインした状態で返す."""
    from bitwarden_sdk import BitwardenClient, DeviceType, client_settings_from_dict

    api_url = os.environ.get("BWS_API_URL", DEFAULT_API_URL)
    identity_url = os.environ.get("BWS_IDENTITY_URL", DEFAULT_IDENTITY_URL)
    token = _require_env("BWS_ACCESS_TOKEN")

    settings = client_settings_from_dict(
        {
            "apiUrl": api_url,
            "identityUrl": identity_url,
            "userAgent": "moneyforward-bws/0.1",
            "deviceType": DeviceType.SDK,
        }
    )
    client = BitwardenClient(settings)
    client.auth().login_access_token(token)
    return client


def list_identifiers(client: BitwardenClient, organization_id: str) -> list:
    """Project 内 secret のメタデータ一覧 (value 含まない)."""
    response = client.secrets().list(organization_id)
    if response.data is None:
        raise BwsApiError("BWS list response empty")
    return list(response.data.data)


def fetch_normal_secrets(
    client: BitwardenClient, organization_id: str
) -> dict[str, str]:
    """`MONEYFORWARD_*` を一括取得し、prefix 剥離済の key -> value マップを返す.

    Returns
    -------
    dict[str, str]
        prefix 剥離済の key -> value マップ (例: ``{"ACCOUNTS": "...json..."}``)
    """
    identifiers = list_identifiers(client, organization_id)

    target_ids = [s.id for s in identifiers if s.key.startswith(BWS_KEY_PREFIX)]

    if not target_ids:
        return {}

    response = client.secrets().get_by_ids(target_ids)
    if response.data is None:
        raise BwsApiError("BWS get_by_ids response empty")

    secrets_map: dict[str, str] = {}
    for secret in response.data.data:
        if not secret.value:
            raise BwsApiError(f"BWS secret value is empty: key={secret.key}")
        app_key = secret.key.removeprefix(BWS_KEY_PREFIX)
        secrets_map[app_key] = secret.value

    return secrets_map


def fetch_secret_value(client: BitwardenClient, secret_id: str) -> str:
    """secret_id 単体で value を取得."""
    response = client.secrets().get(secret_id)
    if response.data is None:
        raise BwsApiError(f"BWS get response empty for id={secret_id}")
    return response.data.value
