# 自動モードの場合

## Work Completion Guidelines

**Critical**: Ensure all work is properly verified before reporting completion.

- **Test Creation**: After creating tests, always run
  `.venv-win/Scripts/pytest.exe tests/ -v` to verify they pass.
- **Code Implementation**: After writing code, always verify:
  - Code lints cleanly (`.venv-win/Scripts/ruff.exe check src/ tests/`)
  - Type checks cleanly (`.venv-win/Scripts/pyright.exe src/ tests/`)
  - Related tests pass (`.venv-win/Scripts/pytest.exe tests/ -v`)
  - No obvious runtime errors
- **Coverage**: Maintain `pytest --cov=src/moneyforward_pk` at 75% or higher.
- **Retry Policy**: 問題発生時は自動で最大5回まで再試行し、それでも
  解消できない場合にのみユーザーへ連絡する (途中経過は報告しない)。
  - Report to user: "同じエラーが5回続いています。別のアプローチが必要かもしれません。"
- **Never report completion** with:
  - Failing tests (unless explicitly creating tests for unimplemented features)
  - Lint or pyright errors
  - Unresolved errors from previous attempts

## Loop Workflow

`plan/rules/RULES0_LOOP.md` orchestrates the planning → programming → review
→ scoring loop via `/loop`. State lives in `plan/CURRENT_ITERATION.md`; each
step overwrites only its own fields. User directives go in
`plan/USER_DIRECTIVES.md` and override the scoring rubric.

See `CONTRIBUTING.md` for the contributor workflow and
`plan/rules/RULES{1..5}_*.md` for individual step rules.

## Project Constraints

- This is a Python / Scrapy / scrapy-playwright project. There is no
  Flutter, Dart, or fvm tooling here.
- Sandbox edits to `scrapy_moneyforward_pk/` only. The legacy
  `../scrapy_moneyforward` project is read-only reference material.
- Do not commit `pyproject.toml` changes that conflict with uncommitted
  user edits; addopts changes are deferred until the user resolves them.
- Do not edit `plan/rules/RULES1_BASIC.md` (user-owned).

# 人間と対話の場合


## プロジェクトルール

### プラン作成

- 保存先: `plan/YYYYMMDD_HHMM_概要.md`（時刻: `date +%Y%m%d_%H%M`）
- 開始時: 【プラン作成モード開始】を応答

### issue 登録

- ユーザー価値・機能単位で分割。細かい準備/docs 追従は本体 issue に吸収
- issue 本文に「関連資料」セクションで `plan/` ファイルへリンク
- ラベル: `feat` / `fix` / `refactor` / `test` / `chore` / `docs`

### 実装フロー

1. ブランチ名提案 → 決定: 人間
2. 設計・実装・レビュー・テスト
3. **プラン完了マーク**: コミット前に `plan/` 該当 issue へ `[完了 PR#XX YYYY-MM-DD]` 追記
4. コミット・マージ: 人間判断

- プラン議論中は実装着手しない（コード diff・新規ファイル生成禁止）
- 実装フェーズはユーザー明示指示後のみ開始
- `commit` / `push` / `merge` / `rebase` / PR 作成はユーザー明示指示まで実行しない
- 実装完了後: push → PR → master マージ → `git pull`
- **プランと実態が乖離したら即時 `plan/` 更新（確認不要）**
- PR 未作成のまま merge 禁止
- squash merge 禁止（merge commit を使う）
- **他エージェントへの依頼は人間の明示指示時のみ**

### ブランチ命名

`feature/[issue番号]_[概要]` / `fix/[issue番号]_[概要]`

### ブランチ運用 (重要)

- **master/main 直 commit 禁止**。コミット前に必ず `git branch --show-current` で確認
- `gh pr merge --delete-branch` 後、HEAD は自動的に master に戻る → 次の作業前に必ず新ブランチ切る
- 過去事例: PR #4 マージ後に master 直 commit 発生 (PR #33 で巻き戻し済)

### コミット規則

Conventional Commits: `feat:` / `fix:` / `chore:` など。

### 実装コミットへの plan/* 同梱

- 実装コミットには対応する `plan/*.md` も `git add` する (RULES3_PROGRAMMING.md と整合)
- 過去事例: plan/* untracked 16件累積 (PR #37 で backfill + RULES3 修正済)

### .env 編集時の半角チェック

- 半角英数字のみ。日本語 IME を切ってから編集
- 過去事例: `MONEYFORWARD_HEADLESS=ｆalse` (全角ｆ) で headless 解除されない不具合
- 確認: `grep -nE "[Ａ-Ｚａ-ｚ０-９]" .env` で全角混入検出

### Spider 起動範囲

- `job_runner.sh` 対応: mf_* 3 個 (transaction / asset / account) のみ
- xmf_* 27 個 (9 partner portal × 3 種別) は `scrapy crawl xmf_xxx_xxx` で個別起動
- 全 variant 循環ロジックは未実装 (将来課題)

### 破壊的操作の鉄則

削除・上書き・切り捨てを含む設計はコード前に人間へ危険性を説明し、安全側を提案。

1. **事前説明**: 消失リスクに気づいたらコード前に伝える
2. **安全側に倒す**: 削除より移動・アーカイブ。上書き前にバックアップ。`-Force` より `-WhatIf`
3. **2ステップ順序保証**: 保存成功しない限り削除しない設計
