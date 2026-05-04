# Bitwarden Secrets Manager 統合

## 概要

`smbcnikko_pk` の `secrets/` モジュールを参考に、本PJへ Bitwarden Secrets Manager (BWS) による設定情報取得を移植する。  
`SECRETS_BACKEND` 未設定時は `"env"` fallback（既存の `.env` / `config/accounts.yaml` で変わらない）。

---

## 差異分析

### smbcnikko_pk との主要差異

| 項目 | smbcnikko_pk | 本PJ |
|------|-------------|------|
| 複数アカウント | 不要（単一 SITE_TORI_PASS） | 必要（site × user[] × pass[]） |
| Secret 構造 | key=value 1:1 | 1 secret = JSON object |
| BWS key prefix | `SMBCNIKKO_` | `MONEYFORWARD_` |
| AWS 認証情報 | 必要（DynamoDB） | 不要 |
| AUTH_PREFIX 機構 | 必要（WebAuthn passkey） | **移植しない**（MoneyForward に WebAuthn 認証なし） |
| Slack webhook | resolver 経由 | `.env` 直接参照（→ resolver 経由に変更） |
| 設定取得関数 | `resolver.get(key)` | `load_accounts(yaml_path)` |
| 認証情報ファイル | なし（BWS のみ） | `config/accounts.yaml`（env mode で継続利用） |
| SECRETS_BACKEND 未設定 | **例外（fail-loud）** | **`"env"` fallback に改変** |

### 重要な設計差異: 複数アカウント構造

smbcnikko_pk は `key → single string value` の 1:1 マッピングで済むが、
本PJは `site → [{user, pass}, ...]` のネスト構造が必要。

**BWS 格納方式（採用案）**:  
`MONEYFORWARD_ACCOUNTS` という単一 secret に、現 YAML 構造を JSON 文字列として格納。

```json
{
  "xmf_ssnb": [
    {"user": "service@example.com", "pass": "secret1"},
    {"user": "finance@example.com", "pass": "secret2"}
  ],
  "mf": [
    {"user": "admin@example.com", "pass": "secret3"}
  ]
}
```

Slack webhook は個別 key で格納（オプション）:
```
MONEYFORWARD_SLACK_INCOMING_WEBHOOK_URL = "https://hooks.slack.com/..."
```

### BWS key prefix 剥離後の app_key 対応表

BWS 上の key 名 → `removeprefix("MONEYFORWARD_")` → app_key:

| BWS key | app_key |
|---------|---------|
| `MONEYFORWARD_ACCOUNTS` | `ACCOUNTS` |
| `MONEYFORWARD_SLACK_INCOMING_WEBHOOK_URL` | `SLACK_INCOMING_WEBHOOK_URL` |

---

## 実装設計

### 新規追加ファイル

```
src/moneyforward/secrets/
├── __init__.py
├── bws_provider.py      # Bitwarden SDK ラッパー（AUTH_PREFIX 機構は移植しない）
├── resolver.py          # dual mode (env / bitwarden) 制御
└── exceptions.py        # SecretsError, SecretNotFoundError

tools/secrets/
└── bws_tool.py          # CLI: list / read / register / dump / delete
                         # register 時: JSON parse + VARIANTS バリデーション
```

### 変更対象ファイル

- `src/moneyforward/_runner_core.py`: `load_accounts()` を resolver 対応に拡張
- `src/moneyforward/settings.py`: `SLACK_INCOMING_WEBHOOK_URL` を resolver 経由に変更（後述の分岐仕様参照）
- `requirements.txt`: `bitwarden-sdk==2.0.0` 追加（smbcnikko_pk と同バージョン pin）
- `.env.example`: BWS 関連環境変数追記

### resolver.py 設計（smbcnikko_pk からの改変点）

```python
# 改変1: SECRETS_BACKEND 未設定は "env" fallback（smbcnikko は fail-loud）
backend = os.environ.get("SECRETS_BACKEND", "env")

# 改変2: REQUIRED_KEYS から SLACK_INCOMING_WEBHOOK_URL を除外
#         Slack は Optional → 未登録でも bootstrap を落とさない
REQUIRED_KEYS = ("ACCOUNTS",)

# 改変3: AUTH_PREFIX 機構 (acquire_webauthn_credentials) は実装しない

# 改変4: テスト用 reset_for_test() は移植する（global 状態のリセット）
```

`bootstrap()` → `get(key)` → `load_accounts_from_resolver()` の流れ。  
`get("SLACK_INCOMING_WEBHOOK_URL")` は `SecretNotFoundError` を呼び出し側で catch（extension の `NotConfigured` dormant 化と整合）。

### settings.py の Slack webhook 分岐仕様

**重要**: settings.py は pytest collection 時にも import されるため、`bootstrap()` をトップレベルで呼ばない。

```python
# settings.py での実装方針
# - トップレベルでは resolver を呼ばない
# - SLACK_INCOMING_WEBHOOK_URL は lazy 取得 or extension 側で resolver.get() を呼ぶ

# 方針: settings.py は既存の os.environ.get() のまま
# extension (slack_notifier_extension.py) 側で resolver.get() に変更
# → extension は「変更あり」に分類変更
SLACK_INCOMING_WEBHOOK_URL = os.environ.get("SLACK_INCOMING_WEBHOOK_URL", "")
```

### _runner_core.py 変更

`load_accounts(yaml_path)` を拡張し、`SECRETS_BACKEND=bitwarden` の場合は
resolver から JSON を取得してパースする。

- シグネチャ: `load_accounts(yaml_path: str | Path | None = None)`
- bitwarden mode: `yaml_path` 引数は無視（warning ログのみ）
- JSON パース後も既存の VARIANTS / user / pass バリデーションロジックを通す（共通化）
- **ACCOUNTS の値（JSON 生文字列）はログ出力禁止**（`Account.password repr=False` との整合）

### slack_notifier_extension.py 変更

`crawler.settings.get("SLACK_INCOMING_WEBHOOK_URL", "")` → `resolver.get("SLACK_INCOMING_WEBHOOK_URL")` に変更し、`SecretNotFoundError` で `NotConfigured` raise（既存の dormant 化挙動を維持）。

---

## 環境変数

### bitwarden mode 必須

```bash
SECRETS_BACKEND=bitwarden
BWS_ACCESS_TOKEN=<machine account token>
ORGANIZATION_ID=<bitwarden organization UUID>
```

### Optional（EU region / デフォルト US）

```bash
BWS_API_URL=https://api.bitwarden.eu
BWS_IDENTITY_URL=https://identity.bitwarden.eu
```

### env mode（デフォルト、既存動作）

```bash
# SECRETS_BACKEND=env  # 省略可、未設定時も env として動作
```

### .env.example 追記内容

```bash
# --- Bitwarden Secrets Manager (bitwarden mode 時のみ必須) ---
# SECRETS_BACKEND=bitwarden
# BWS_ACCESS_TOKEN=<machine account access token>
# ORGANIZATION_ID=<bitwarden organization UUID>
# BWS_API_URL=https://api.bitwarden.eu       # EU region 使用時
# BWS_IDENTITY_URL=https://identity.bitwarden.eu  # EU region 使用時
```

全角混入確認: `grep -nE "[Ａ-Ｚａ-ｚ０-９]" .env.example`

---

## 実装ステップ

1. `requirements.txt`: `bitwarden-sdk==2.0.0` 追加
2. `src/moneyforward/secrets/exceptions.py` 作成
3. `src/moneyforward/secrets/bws_provider.py` 作成
   - `SMBCNIKKO_` → `MONEYFORWARD_` 置換
   - import path を `moneyforward.secrets.*` に変更
   - `AUTH_PREFIX` / `acquire_webauthn_credentials` は実装しない
4. `src/moneyforward/secrets/resolver.py` 作成
   - `SECRETS_BACKEND` デフォルト `"env"` に改変
   - `REQUIRED_KEYS = ("ACCOUNTS",)` のみ（Slack は除外）
   - `ACCOUNTS` JSON パース → VARIANTS バリデーション
   - `reset_for_test()` 移植
5. `src/moneyforward/_runner_core.py`: `load_accounts()` を resolver 対応に拡張
6. `src/moneyforward/extensions/slack_notifier_extension.py`: resolver.get() に変更
7. `tools/secrets/bws_tool.py` 作成
   - register コマンド: JSON parse + VARIANTS バリデーション追加
8. `.env.example` 更新
9. テスト作成
   - resolver: env mode / bitwarden mode（mock）
   - `reset_for_test()` を各テストで使用
   - `ACCOUNTS` JSON バリデーション（不正 site / user/pass 欠損）
10. lint / pyright / pytest 通過確認（カバレッジ 75% 以上維持）

---

## 非変更範囲

- `config/accounts.yaml`: env mode で引き続き使用（削除しない）
- 既存 spider・middleware・pipeline: 変更なし
- `src/moneyforward/settings.py`: Slack webhook は変更しない（extension 側で対処）
- CI: デフォルト `SECRETS_BACKEND=env` で動作するため変更不要

---

## Opus レビュー指摘（反映済）

- [高] settings.py での BWS API 呼出回避 → extension 側で resolver.get() に変更
- [高] REQUIRED_KEYS から `SLACK_INCOMING_WEBHOOK_URL` 除外 → Slack は optional
- [高] SECRETS_BACKEND デフォルト "env" fallback → smbcnikko 実装を改変
- [中] AUTH_PREFIX 機構は移植しない旨を明記
- [中] ACCOUNTS 値のログ禁止を明記
- [中] load_accounts() シグネチャ変更の後方互換（bitwarden mode は yaml_path 無視）
- [中] JSON パース後も VARIANTS バリデーションを通す
- [中] BWS key prefix 剥離後の app_key 対応表を追記
- [低] reset_for_test() 移植
- [低] .env.example の具体的追記内容を明記
- [低] import path 全置換を明記
- [低] bws_tool.py の register に JSON + VARIANTS バリデーション追加

---

## 関連資料

- [issue #59](https://github.com/genba-neko/scrapy_moneyforward_pk/issues/59)
- smbcnikko_pk 参照実装: `c:\Users\g\OneDrive\devel\genba-neko@github\scrapy_smbcnikko_pk\src\smbcnikko\secrets\`
- bws_tool.py 参照: `c:\Users\g\OneDrive\devel\genba-neko@github\scrapy_smbcnikko_pk\tools\secrets\bws_tool.py`
