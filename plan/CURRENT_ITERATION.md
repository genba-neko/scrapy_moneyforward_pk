# CURRENT_ITERATION.md — イテレーション状態

RULES0_LOOP がこのファイルを毎ターン読んで次ステップを決定する。
各ステップは担当フィールドだけ上書きする。他フィールドは触らない。

---

## 累積フィールド (キャンペーン全体で保持・リセットしない)

```yaml
iteration_count: 0           # RULES2 がイテレーション開始時に +1
completion_status: CONTINUE  # RULES5 が設定: CONTINUE / DONE / TIMEOUT

out_of_scope: []             # RULES2 が初回宣言。以降引き継ぐ
adjusted_ceilings:           # RULES2 が初回計算。以降引き継ぐ
  コード品質: 100
  テスト品質: 100
  機能移植率: ~
  スパイダー正確性: 100
  セキュリティ: 100
  運用CI: ~
  設計拡張性: 100
  ドキュメント: 100

closed_issues: []            # RULES3 がコミット時に追記。リセットしない
```

## イテレーション毎フィールド (RULES2 が新イテレーション開始時にリセット)

```yaml
# --- ステップ参照 ---
plan_file: ""               # RULES2 が設定
review_file: ""             # RULES4 が設定
scoring_file: ""            # RULES5 が設定
previous_scoring_file: ""   # RULES2 が新イテ開始時に前回 scoring_file をコピー (前回比較用)

# --- 実装状態 ---
current_step: initial_scoring  # initial_scoring / planning / programming / review / scoring
programming_status: ""         # "" / in_progress / done
completed_tasks: []
skipped_tasks: []    # [{task, reason, action}]

# --- レビュー状態 ---
review_status: ""       # "" / PASS / FAIL
review_fail_count: 0    # RULES0 が FAIL 再入時にカウント。2回超で強制 PASS
review_blockers: []     # [{file, line, issue, fix, related_task}]

# --- Issue 追跡 ---
open_issues: []      # RULES2 が gh issue create 後に設定
                     # RULES3 がコミット時に closed_issues へ移動
```

## スコア (RULES5 が更新)

```yaml
scores:
  コード品質: ~
  テスト品質: ~
  機能移植率: ~
  スパイダー正確性: ~
  セキュリティ: ~
  運用CI: ~
  設計拡張性: ~
  ドキュメント: ~
  合計: ~
adjusted_scores:
  調整後合計: ~
  調整後上限: ~
```

---

## ライフサイクル

```
[キャンペーン開始]
  RULES0 が CURRENT_ITERATION.md を存在確認
  → なければ rules/CURRENT_ITERATION_TEMPLATE.md からコピーして作成

[イテレーション N 開始 (RULES2)]
  iteration_count += 1
  previous_scoring_file = {前回 scoring_file の値}  # RULES2 がコピー
  plan_file / review_file / scoring_file = ""
  programming_status = ""
  completed_tasks = []
  skipped_tasks = []
  review_status = ""
  review_fail_count = 0
  review_blockers = []
  open_issues = []
  # closed_issues / out_of_scope / adjusted_ceilings は引き継ぐ

[各ステップ]
  担当フィールドだけ上書き

[DONE / TIMEOUT]
  RULES5 が PR 作成後にリネーム:
  CURRENT_ITERATION.md → plan/YYYYMMDD_HHMM_iteration_log.md
  (次キャンペーンまで CURRENT_ITERATION.md は存在しない)
```

## 完了判定ルール (RULES5 が自動設定)

```
全カテゴリ 調整後スコア >= 80 かつ Critical 欠陥ゼロ → DONE
iteration_count >= 5 かつ未達                        → TIMEOUT
それ以外                                             → CONTINUE
```

## 更新履歴

| iter | 日時 | 合計 | 調整後 | 完了 |
|---|---|---|---|---|
| 0 (初期) | 2026-04-25 | - | - | CONTINUE |
