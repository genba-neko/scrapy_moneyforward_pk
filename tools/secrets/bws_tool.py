"""Bitwarden Secrets Manager 運用ツール.

subcommand:
- list:     project 内の secret メタデータ一覧
- read:     key 名で secret 値取得
- register: secret 登録 (同名 key あれば update、なければ create)
            ACCOUNTS key の場合は JSON parse + VARIANTS バリデーションを実行
- dump:     prefix で絞った全件取得
- delete:   key 名で secret 削除

環境変数:
- BWS_ACCESS_TOKEN  (必須) machine account の access token
- ORGANIZATION_ID   (必須) Bitwarden organization UUID
- BWS_PROJECT_ID    (register 時必須) 登録先 project UUID
- BWS_API_URL       (任意) デフォルト https://api.bitwarden.com (US)
- BWS_IDENTITY_URL  (任意) デフォルト https://identity.bitwarden.com (US)

EU リージョン使用時:
  BWS_API_URL=https://api.bitwarden.eu
  BWS_IDENTITY_URL=https://identity.bitwarden.eu
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# プロジェクトルート (= tools/ の親) の .env を読み込む。
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# src/ を sys.path に追加して moneyforward パッケージを参照可能にする。
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

DEFAULT_API_URL = "https://api.bitwarden.com"
DEFAULT_IDENTITY_URL = "https://identity.bitwarden.com"

from moneyforward.secrets.bws_provider import BWS_KEY_PREFIX  # noqa: E402


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.stderr.write(f"環境変数未設定: {name}\n")
        sys.exit(2)
    return value


def get_client() -> Any:
    """BitwardenClient を初期化して access token でログイン."""
    from bitwarden_sdk import BitwardenClient, DeviceType, client_settings_from_dict

    api_url = os.environ.get("BWS_API_URL", DEFAULT_API_URL)
    identity_url = os.environ.get("BWS_IDENTITY_URL", DEFAULT_IDENTITY_URL)
    token = _require_env("BWS_ACCESS_TOKEN")

    settings = client_settings_from_dict(
        {
            "apiUrl": api_url,
            "identityUrl": identity_url,
            "userAgent": "moneyforward-bws-tool/0.1",
            "deviceType": DeviceType.SDK,
        }
    )
    client = BitwardenClient(settings)
    client.auth().login_access_token(token)
    return client


def _list_identifiers(client: Any, org_id: str) -> list[Any]:
    response = client.secrets().list(org_id)
    return list(response.data.data)


def _resolve_id_by_key(client: Any, org_id: str, key: str) -> str | None:
    for s in _list_identifiers(client, org_id):
        if s.key == key:
            return str(s.id)
    return None


def _validate_accounts_json(value: str) -> None:
    """ACCOUNTS key 登録時の JSON + VARIANTS バリデーション."""
    from moneyforward.spiders.variants.registry import VARIANTS

    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"JSON パース失敗: {exc}\n")
        sys.exit(2)

    if not isinstance(data, dict):
        sys.stderr.write(
            f"ACCOUNTS は dict である必要がある (got {type(data).__name__})\n"
        )
        sys.exit(2)

    unknown = sorted(set(data) - set(VARIANTS))
    if unknown:
        sys.stderr.write(f"未知の site キー: {unknown}; known={sorted(VARIANTS)}\n")
        sys.exit(2)


def cmd_list(_args: argparse.Namespace) -> int:
    """Project 内 secret のメタデータ一覧を出力."""
    org_id = _require_env("ORGANIZATION_ID")
    client = get_client()
    identifiers = _list_identifiers(client, org_id)
    output = [
        {
            "id": str(s.id),
            "key": s.key,
            "organization_id": str(s.organization_id),
        }
        for s in identifiers
    ]
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n[total: {len(output)} secrets]", file=sys.stderr)
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    """Key 名で secret 値を取得.

    警告: value は平文で stdout に出力される。ターミナル履歴・ログファイル・
    スクリーン共有に残るリスクがある。ACCOUNTS key は全アカウントの認証情報を含む。
    """
    sys.stderr.write(
        "警告: secret 値を平文で出力します。端末履歴に残ることに注意してください。\n"
    )
    org_id = _require_env("ORGANIZATION_ID")
    client = get_client()
    secret_id = _resolve_id_by_key(client, org_id, args.key)
    if secret_id is None:
        sys.stderr.write(f"key 該当なし: {args.key}\n")
        return 1
    response = client.secrets().get(secret_id)
    secret = response.data
    print(
        json.dumps(
            {
                "id": str(secret.id),
                "key": secret.key,
                "value": secret.value,
                "note": getattr(secret, "note", None),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    """Secret 登録 (同名 key あれば update、なければ create).

    ACCOUNTS key の場合は JSON/YAML parse + VARIANTS バリデーションを実行してから登録。
    --from-yaml は config/accounts.yaml をそのまま渡せる。
    """
    org_id = _require_env("ORGANIZATION_ID")
    project_id = _require_env("BWS_PROJECT_ID")

    if args.from_yaml:
        import yaml as _yaml

        raw = _yaml.safe_load(Path(args.from_yaml).read_text(encoding="utf-8")) or {}
        value = json.dumps(raw, ensure_ascii=False)
    elif args.from_file:
        value = Path(args.from_file).read_text(encoding="utf-8")
    elif args.value is not None:
        value = args.value
    else:
        sys.stderr.write(
            "--value / --from-file / --from-yaml のいずれかを指定すること\n"
        )
        return 2

    # ACCOUNTS key は JSON + VARIANTS の事前バリデーション
    bws_key = f"{BWS_KEY_PREFIX}{args.key}"
    if args.key == "ACCOUNTS":
        _validate_accounts_json(value)

    note = args.note or ""
    client = get_client()
    existing_id = _resolve_id_by_key(client, org_id, bws_key)
    if existing_id:
        response = client.secrets().update(
            org_id, existing_id, bws_key, value, note, [project_id]
        )
        op = "updated"
    else:
        response = client.secrets().create(org_id, bws_key, value, note, [project_id])
        op = "created"
    secret = response.data
    print(
        json.dumps(
            {"operation": op, "id": str(secret.id), "key": secret.key},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    """Prefix で絞った secrets を全件取得して JSON 出力.

    警告: value は平文で stdout に出力される。MONEYFORWARD_ACCOUNTS を含む場合、
    全アカウントの認証情報が平文で出力されるため取り扱いに注意。
    """
    sys.stderr.write(
        "警告: secret 値を平文で出力します。端末履歴に残ることに注意してください。\n"
    )
    org_id = _require_env("ORGANIZATION_ID")
    client = get_client()
    identifiers = _list_identifiers(client, org_id)
    prefix = args.prefix or BWS_KEY_PREFIX
    targets = [s for s in identifiers if s.key.startswith(prefix)]
    output: list[dict[str, Any]] = []
    for s in targets:
        get_response = client.secrets().get(str(s.id))
        full = get_response.data
        output.append({"id": str(full.id), "key": full.key, "value": full.value})
    print(json.dumps(output, ensure_ascii=False, indent=2))
    print(
        f"\n[matched: {len(output)} / total in project: {len(identifiers)}]",
        file=sys.stderr,
    )
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    """Key 名で secret を削除."""
    org_id = _require_env("ORGANIZATION_ID")
    bws_key = f"{BWS_KEY_PREFIX}{args.key}"
    client = get_client()
    secret_id = _resolve_id_by_key(client, org_id, bws_key)
    if secret_id is None:
        sys.stderr.write(f"key 該当なし: {bws_key}\n")
        return 1
    response = client.secrets().delete([secret_id])
    print(
        json.dumps(
            {"deleted_id": secret_id, "key": bws_key, "response": str(response.data)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bws_tool",
        description="Bitwarden Secrets Manager 運用ツール",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="project 内 secret のメタデータ一覧")

    p_read = sub.add_parser("read", help="key 名で secret 値を取得 (prefix なしで指定)")
    p_read.add_argument("--key", required=True, help="app key 名 (例: ACCOUNTS)")

    p_reg = sub.add_parser("register", help="secret 登録 (同名 key あれば update)")
    p_reg.add_argument("--key", required=True, help="app key 名 (例: ACCOUNTS)")
    p_reg.add_argument("--value", help="secret 値 (JSON 文字列)")
    p_reg.add_argument("--from-file", help="JSON ファイルから値を読み込む")
    p_reg.add_argument(
        "--from-yaml",
        help="YAML ファイルから読み込んで JSON に変換して登録 (config/accounts.yaml 向け)",
    )
    p_reg.add_argument("--note", help="メモ")

    p_dump = sub.add_parser("dump", help="prefix で絞った全件取得")
    p_dump.add_argument(
        "--prefix",
        default=BWS_KEY_PREFIX,
        help=f"BWS key prefix (デフォルト: {BWS_KEY_PREFIX})",
    )

    p_del = sub.add_parser("delete", help="key 名で secret を削除")
    p_del.add_argument("--key", required=True, help="app key 名 (例: ACCOUNTS)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "read":
        return cmd_read(args)
    if args.command == "register":
        return cmd_register(args)
    if args.command == "dump":
        return cmd_dump(args)
    if args.command == "delete":
        return cmd_delete(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
