# tools/secrets/bws_tool.py

Bitwarden Secrets Manager (BWS) の管理操作 CLI。
`src/moneyforward/secrets/` は runtime 読み込み専用のため、secret の登録・確認・削除は本ツールで行う。

## 前提

```bash
# .env または環境変数に設定
BWS_ACCESS_TOKEN=<machine account の access token>   # 必須
ORGANIZATION_ID=<Bitwarden organization UUID>         # 必須
BWS_PROJECT_ID=<登録先 project UUID>                  # register 時必須

# EU リージョン使用時のみ
BWS_API_URL=https://api.bitwarden.eu
BWS_IDENTITY_URL=https://identity.bitwarden.eu
```

## 実行方法

```bash
# Windows (.venv-win)
.venv-win/Scripts/python.exe tools/secrets/bws_tool.py <subcommand>
```

## サブコマンド

### list — メタデータ一覧

```bash
python tools/secrets/bws_tool.py list
```

project 内の secret ID / key 一覧を JSON 出力（value は含まない）。

---

### read — 値取得

```bash
python tools/secrets/bws_tool.py read --key ACCOUNTS
```

`MONEYFORWARD_<key>` の value を平文で stdout に出力。
**警告**: 端末履歴・スクリーン共有に残るリスクあり。

---

### register — 登録 / 更新

同名 key が存在すれば update、なければ create。

```bash
# 直接値を指定
python tools/secrets/bws_tool.py register --key ACCOUNTS --value '{"mf": [...]}'

# ファイルから読み込む
python tools/secrets/bws_tool.py register --key ACCOUNTS --from-file accounts.json

# config/accounts.yaml をそのまま登録 (YAML→JSON 変換)
python tools/secrets/bws_tool.py register --key ACCOUNTS --from-yaml config/accounts.yaml
```

`ACCOUNTS` key は登録前に JSON parse + `VARIANTS` バリデーションを実行。

---

### dump — prefix 絞り込み全件取得

```bash
python tools/secrets/bws_tool.py dump
# prefix 指定 (デフォルト: MONEYFORWARD_)
python tools/secrets/bws_tool.py dump --prefix MONEYFORWARD_
```

**警告**: ACCOUNTS を含む場合、全認証情報が平文出力される。

---

### delete — 削除

```bash
python tools/secrets/bws_tool.py delete --key ACCOUNTS
```

`MONEYFORWARD_<key>` を削除。取消不可。

## BWS key の命名規則

すべての secret は `MONEYFORWARD_` プレフィックス付きで保存される。

| app key | BWS key |
|---|---|
| `ACCOUNTS` | `MONEYFORWARD_ACCOUNTS` |
| `SLACK_INCOMING_WEBHOOK_URL` | `MONEYFORWARD_SLACK_INCOMING_WEBHOOK_URL` |
