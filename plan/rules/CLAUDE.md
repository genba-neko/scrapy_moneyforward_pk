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
- **Coverage**: Maintain `pytest --cov=src/moneyforward` at 75% or higher.
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
`plan/rules/USER_DIRECTIVES.md` and override the scoring rubric.

See `CONTRIBUTING.md` for the contributor workflow and
`plan/rules/RULES{1..5}_*.md` for individual step rules.

## Project Constraints

- This is a Python / Scrapy / scrapy-playwright project. There is no
  Flutter, Dart, or fvm tooling here.
- Sandbox edits to `src/moneyforward/` only. The legacy
  `../scrapy_moneyforward` project is read-only reference material.
- Do not commit `pyproject.toml` changes that conflict with uncommitted
  user edits; addopts changes are deferred until the user resolves them.
- Do not edit `plan/rules/RULES1_BASIC.md` (user-owned).
