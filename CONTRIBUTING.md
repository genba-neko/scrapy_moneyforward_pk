# CONTRIBUTING

`scrapy_moneyforward_pk` への変更手順 (社内開発者向け)。

## 開発環境

- Python 3.10+ (3.11 推奨)
- Windows のローカル仮想環境は `.venv-win/` 固定 (pyproject.toml に
  `venv = ".venv-win"` 設定あり)
- 依存は `requirements.txt` から install

```powershell
python -m venv .venv-win
.venv-win\Scripts\pip install -r requirements.txt
.venv-win\Scripts\python -m playwright install chromium
```

## テスト・lint

3 本のコマンドが全て clean を維持する:

```powershell
.venv-win\Scripts\pytest tests/ -v
.venv-win\Scripts\ruff check src/ tests/
.venv-win\Scripts\pyright src/ tests/
```

カバレッジ確認:

```powershell
.venv-win\Scripts\pytest tests/ --cov=src/moneyforward_pk --cov-report=term-missing
```

カバレッジは現状 86%、PR では 75% 以上を維持する。

## コミット

- Conventional Commits: `<type>(<scope>): <subject>` (50 文字以内・英語・命令形)
  - type: `feat` / `fix` / `refactor` / `test` / `docs` / `chore`
  - 例: `fix(parsers): accept tr.transaction_list shape (closes #8)`
- 1 タスク = 1 コミット原則。`pytest` + `ruff` clean を確認してからコミット
- 関連 Issue は `closes #N` (最終コミット) / `refs #N` (途中) で紐付け
- pre-commit hook を必ず通す (`--no-verify` 禁止)

## ループ運用 (`/loop`)

`plan/rules/RULES0_LOOP.md` を `/loop` で起動するとプラン → 実装 →
レビュー → 採点が自動で 1 イテレーション回る。状態は
`plan/CURRENT_ITERATION.md` に集約され、各ステップが担当フィールドだけ
上書きする。詳細は `plan/rules/RULES{0..5}_*.md` を参照。

ユーザー指示は `plan/USER_DIRECTIVES.md` に書いておくと RULES2 が必ず
読み、採点基準より優先される。

## 変更ロック

iter プランが `変更ロック` に列挙したファイル以外を編集するな。
ロック外を変えたい場合はプランへタスクを追記してから次イテレーションで
対処する (RULES3 のスコープクリープ禁止に従う)。

## ログのセキュリティ

新規 logger を直接生成 (`logging.getLogger("foo")`) する場合、
`setup_common_logging` 経由で root に attach 済みの
`utils/log_filter.SensitiveDataFilter` が伝搬する。明示的に attach する
必要は通常ないが、独自 handler を root バイパスで追加する場合は

```python
from moneyforward_pk.utils.log_filter import attach_sensitive_filter

logger = logging.getLogger("custom.handler.path")
attach_sensitive_filter(logger)
```

を追加して URL / cookie / Authorization / password の生値が落ちないことを
確認する。`logger.exception` 経由のスタックトレースは Scrapy の標準フォー
マッタが record.msg を経由するので redaction が効く。テストで挙動を確認
したい場合は `tests/test_logger_filter_unit.py` をコピーして拡張する。

## DynamoDB スキーマ

本番テーブルのキー設計は変更禁止 (RULES3 参照):

- `transaction`: PK = `year_month`, SK = `data_table_sortable_value`
- `asset_allocation`: PK = `year_month_day`, SK = `asset_item_key`
- `account`: PK = `year_month_day`, SK = `account_item_key`

JSON Lines 出力 (現行) もこのキー名で揃えてあるので、上流で互換を保つ
ためにフィールド名を変えないこと。
