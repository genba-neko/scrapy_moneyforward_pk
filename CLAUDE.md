## Work Completion Guidelines
**Critical**: Ensure all work is properly verified before reporting completion
- **Test Creation**: After creating tests, always run `cd app && fvm flutter test` to verify they pass
- **Code Implementation**: After writing code, always verify:
  - Code compiles without errors (`cd app && fvm flutter analyze`)
  - Custom lints pass (`cd app && fvm dart run custom_lint`)
  - Related tests pass (`cd app && fvm flutter test`)
  - No obvious runtime errors
- **Retry Policy**: 問題発生時は自動で最大5回まで再試行し、それでも解消できない場合にのみユーザーへ連絡する（途中経過は報告しない）
  - Report to user: "同じエラーが5回続いています。別のアプローチが必要かもしれません。"
- **Never report completion** with:
  - Failing tests (unless explicitly creating tests for unimplemented features)
  - Compilation errors
  - Unresolved errors from previous attempts
