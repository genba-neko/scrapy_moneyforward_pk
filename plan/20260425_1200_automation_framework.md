# 自動化フレームワーク構築

実施日: 2026-04-25

## 目的

スコアリング → プランニング → 実装 → レビュー → 採点 のループを
人間介入なしで自動化するフレームワークを設計・構築。

---

## 成果物

| ファイル | 役割 |
|---|---|
| `plan/rules/RULES0_LOOP.md` | ステートマシン型オーケストレーター (`/loop` で実行) |
| `plan/rules/RULES1_BASIC.md` | 基本ルール・動線・完了条件 |
| `plan/rules/RULES2_PLANNING.md` | 採点+ユーザー指示 → 改善プラン生成 |
| `plan/rules/RULES3_PROGRAMMING.md` | プラン → 実装・コミット |
| `plan/rules/RULES4_REVVUE.md` | 実装 → PASS/FAIL レビュー |
| `plan/rules/RULES5_SCORING.md` | 採点・調整後スコア・完了判定 |
| `plan/CURRENT_ITERATION.md` | イテレーション状態ハブ (ライブ) |
| `plan/rules/CURRENT_ITERATION_TEMPLATE.md` | 新キャンペーン開始用テンプレート |
| `plan/USER_DIRECTIVES.md` | ユーザー指示書 (ループ前後に編集) |

---

## 設計判断

### ステートマシン (RULES0)

全ステップを `current_step` フィールドで管理。条件は全て二値判定:

| 条件 | 次ステップ |
|---|---|
| `iteration_count=0 AND scoring_file=""` | RULES5 (初回採点) |
| `scoring_file="" AND plan_file=""` | RULES2 |
| `plan_file!="" AND prog!="done"` | RULES3 |
| `prog="done" AND review_file=""` | RULES4 |
| `review="FAIL" AND scoring_file=""` | RULES3 (再入) |
| `review="PASS" AND scoring_file=""` | RULES5 |
| `scoring_file!="" AND status="CONTINUE"` | RULES2 (次iter) |
| `status="DONE/TIMEOUT"` | PR作成→リネーム→停止 |

### 完了条件: 調整後スコア

Out-of-scope 項目 (xmf_*・レポート群) の減点を除いた調整後スコアで判定。
生スコア 95 点を要求すると永久ループになるため。

### Issue / PR 戦略

- **Issue**: タスクを論理グループ化 (2〜4 Issue/iter)、細かく切りすぎない
- **コミット**: `closes #N` で Issue と紐づけ
- **PR**: 全イテレーション完了時に1回だけ `gh pr create`、全 Issue を列挙

### USER_DIRECTIVES.md

採点基準より優先される人間の意思決定入力口。
「DynamoDB → JSON 出力」のような設計変更を RULES2 がプランに強制反映。

### ファイルライフサイクル

```
キャンペーン開始:  CURRENT_ITERATION_TEMPLATE.md → CURRENT_ITERATION.md (コピー)
各イテレーション: iter{N}_plan.md / iter{N}_review.md / iter{N}_scoring.md を生成
                  CURRENT_ITERATION.md を上書き更新
キャンペーン完了: CURRENT_ITERATION.md → YYYYMMDD_HHMM_iteration_log.md (リネーム)
次キャンペーン:   CURRENT_ITERATION.md なし → テンプレからコピーして再起動
```

### エラーハンドリング

- タスク実行不能 → `skipped_tasks` に記録してスキップ、停止しない
- RULES4 FAIL → `review_blockers` を YAML 形式で記録、RULES3 が自動読取・修正
- イテレーション上限 (5回) → TIMEOUT として正常完了処理

---

## コーディング規約 (RULES3 で追加)

- PEP 8 準拠
- Numpy 形式 docstring (新規公開関数・クラスに必須)
- インラインコメント: WHY のみ1行
- ruff `D` ルール有効化 (`convention = "numpy"`)、既存 D1xx は後続で解消
- Conventional Commits (`feat/fix/refactor/test/docs/chore`)
- コミットに Issue 番号 (`closes #N` / `refs #N`)
