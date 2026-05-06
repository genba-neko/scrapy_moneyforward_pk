# plan: AXIOM_TOKEN/AXIOM_ORG_ID を Bitwarden から取得 (#73)

## 目的

`_build_axiom_handler()` を `resolver.get()` 経由に切り替え、`SECRETS_BACKEND=bitwarden` 時も AXIOM キーを BWS から取得できるようにする。

## 方針

- `resolver.get(key)` を try/except で包み、失敗時は `os.getenv()` フォールバック
- env mode 既存挙動変更なし
- Axiom は optional → `SecretNotFound` は silent skip

## 変更ファイル

- `src/moneyforward/utils/logging_config.py` — `_build_axiom_handler()` を resolver 経由に変更
- `.env.example` — BWS 登録キー名コメント追記
- `tests/test_logging_axiom_unit.py` — resolver reset fixture 追加、bitwarden path テスト追加

## ステータス

- [x] 実装
- [x] テスト
- [ ] コミット
- [ ] PR 作成
