# CONTRIBUTING

`scrapy_moneyforward_pk` への変更手順 (開発者向け)。

## 開発環境

- Python 3.10+ (3.11 推奨)
- `.venv-win/` 固定 (Windows ローカル)

```powershell
python -m venv .venv-win
.venv-win\Scripts\pip install -r requirements.txt
.venv-win\Scripts\python -m playwright install chromium
```

## テスト・lint

3 本すべて clean を維持する:

```powershell
.venv-win\Scripts\pytest tests/ -v
.venv-win\Scripts\ruff check src/ tests/
.venv-win\Scripts\pyright src/ tests/
```

カバレッジ確認 (PR では 75% 以上を維持):

```powershell
.venv-win\Scripts\pytest tests/ --cov=src/moneyforward --cov-report=term-missing
```

現状: 296 tests, 84% coverage。

## コミット

- Conventional Commits: `<type>(<scope>): <subject>`
  - type: `feat` / `fix` / `refactor` / `test` / `docs` / `chore`
  - 例: `fix(parsers): accept tr.transaction_list shape (closes #8)`
- `pytest` + `ruff` clean を確認してからコミット
- 関連 Issue: `closes #N` (最終コミット) / `refs #N` (途中)
- pre-commit hook を必ず通す (`--no-verify` 禁止)
- 実装コミットには対応 `plan/*.md` も含める

## ループ運用 (`/loop`)

`plan/rules/RULES0_LOOP.md` を `/loop` で起動するとプラン → 実装 →
レビュー → 採点が 1 イテレーション回る。状態は `plan/CURRENT_ITERATION.md`
に集約される。詳細は `plan/rules/RULES{0..5}_*.md` を参照。

ユーザー指示は `plan/rules/USER_DIRECTIVES.md` に記入する。RULES2 が必ず読み
採点基準より優先される。

## 変更ロック

iter プランが `変更ロック` に列挙したファイル以外を編集しない。
ロック外の変更は次イテレーションでプランに追加してから実施する。

## ログのセキュリティ

新規 logger で root バイパスの独自 handler を追加する場合は明示的に
`SensitiveDataFilter` を attach する:

```python
from moneyforward.utils.log_filter import attach_sensitive_filter

logger = logging.getLogger("custom.handler.path")
attach_sensitive_filter(logger)
```

これにより URL / cookie / Authorization / password の生値がログに落ちない。
詳細は `tests/test_logger_filter_unit.py` 参照。

## 出力フィールド名 (上流互換)

出力 Item のフィールド名は前身プロジェクトの DynamoDB キー名に揃えてある。
フィールド名を変更すると上流コンシューマとの互換が壊れる。

詳細は [ARCHITECTURE.md § Field Names](ARCHITECTURE.md#field-names-upstream-compatibility) 参照。
