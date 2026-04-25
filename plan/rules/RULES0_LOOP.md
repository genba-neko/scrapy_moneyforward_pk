# RULES0_LOOP.md — 自動ループオーケストレーター

`/loop` で実行。全イテレーションを人間介入なしで自動化する。

## 毎ターンの処理

### Step 1: 状態読取

`plan/CURRENT_ITERATION.md` を読む。存在しなければ
`plan/rules/CURRENT_ITERATION_TEMPLATE.md` をコピーして作成してから続行。

```yaml
# テンプレートの初期値
iteration_count: 0
current_step: initial_scoring
completion_status: CONTINUE
plan_file: ""
review_file: ""
scoring_file: ""
review_status: ""
programming_status: ""
review_blockers: []
skipped_tasks: []
```

### Step 2: 停止判定

| 条件 | 処理 |
|---|---|
| `completion_status: DONE` | 完了メッセージを出力して `/loop` 終了 |
| `completion_status: TIMEOUT` | タイムアウトサマリーを出力して `/loop` 終了 |
| `iteration_count >= 5` | CURRENT_ITERATION.md に `completion_status: TIMEOUT` を書き込んでから TIMEOUT 処理 → 停止 |

### Step 3: ステップ選択 (状態機械)

```
【ブートストラップ】
scoring_file が空 かつ plan_file が空 かつ iteration_count = 0
  → current_step = initial_scoring → RULES5 を初回採点モードで実行
     (review_status チェックをスキップ。現状把握が目的)

【通常ループ】
scoring_file あり かつ plan_file が空
  → current_step = planning → RULES2 を実行

plan_file あり かつ programming_status が "done" 未満
  → current_step = programming → RULES3 を実行

programming_status = "done" かつ review_file が空
  → current_step = review → RULES4 を実行

review_status = "FAIL" かつ review_fail_count < 2
  → review_fail_count += 1 → current_step = programming (再入) → RULES3 を実行
     (review_blockers を修正対象として読み込む)

review_status = "FAIL" かつ review_fail_count >= 2
  → skipped_tasks に "review FAIL リトライ上限超過" を記録
  → review_status を "PASS" に強制設定 → current_step = scoring → RULES5 を実行

review_status = "PASS" かつ scoring_file = ""
  → current_step = scoring → RULES5 を実行

scoring_file あり かつ completion_status = "CONTINUE"
  → plan_file/review_file をクリア (scoring_file は RULES2 が previous_scoring_file にコピー後クリア)
  → current_step = planning → RULES2 を実行 (次イテレーション)
```

### Step 4: 実行後の検証

各ステップ完了後:
1. `plan/CURRENT_ITERATION.md` を再読して更新を確認
2. 期待するフィールドが埋まっていれば次のターンへ
3. 埋まっていなければそのステップを再実行 (最大2回)
4. 2回失敗したら `skipped_tasks` に記録して次ステップへ強制進行

---

## RULES2 実行内容 (Planning)

`plan/rules/RULES2_PLANNING.md` の全内容を実行。
完了後 CURRENT_ITERATION.md の `plan_file` が設定されることを確認。

## RULES3 実行内容 (Programming)

`plan/rules/RULES3_PROGRAMMING.md` の全内容を実行。

**review_blockers がある場合 (FAIL 差し戻し)**:
CURRENT_ITERATION.md の `review_blockers` を先に読み、
プランのタスクより前にブロッカー修正を実施する。

**タスク実行不能の場合**:
- 原因を `skipped_tasks` に追記
- そのタスクをスキップして次タスクへ
- ユーザー報告で止まらない

完了後 CURRENT_ITERATION.md の `programming_status: done` を確認。

## RULES4 実行内容 (Review)

`plan/rules/RULES4_REVVUE.md` の全内容を実行。
FAIL の場合は `review_blockers` に機械可読形式で記録してから次ターンへ。

## RULES5 実行内容 (Scoring)

`plan/rules/RULES5_SCORING.md` の全内容を実行。
`completion_status` が DONE / CONTINUE / TIMEOUT のいずれかに設定されることを確認。

---

## TIMEOUT 処理

```markdown
# イテレーション完了サマリー (TIMEOUT)

- 実施イテレーション数: {N} / 5
- 最終スコア: {X} / 800 (調整後: {Y})
- 未達カテゴリ: {リスト}
- 未解決タスク (skipped_tasks): {リスト}
- 将来課題: {plan の将来課題セクション}
```

`plan/CURRENT_ITERATION.md` を `plan/YYYYMMDD_HHMM_iteration_log.md` にリネームして `/loop` 終了。

---

## DONE 処理

RULES5 が PR 作成・リネームを実施 (`plan/rules/RULES5_SCORING.md` の「完了時の処理」参照)。
`/loop` を終了する。

---

## ループ満了後の再起動

DONE または TIMEOUT でループが終了した後、再度 `/loop` を実行した場合:

1. `plan/CURRENT_ITERATION.md` が存在しない (リネーム済み)
2. `plan/rules/CURRENT_ITERATION_TEMPLATE.md` からコピーして新規作成
3. `current_step: initial_scoring` から再開
4. 前キャンペーンの iter{N}_*.md / iteration_log.md は plan/ に残り参照可能
5. 新キャンペーンの採点で前回比較が自動的に行われる (RULES5 が前回の scoring を読む)

---

## 制約

- CURRENT_ITERATION.md を読まずに判断しない
- RULES2 実行前に必ず `plan/USER_DIRECTIVES.md` を読む (RULES2 に委譲)
- ユーザーへの確認で止まらない (判断できないものはスキップして記録)
- 1ターンで1ステップのみ実行 (複数ステップを1ターンに詰め込まない)
- 各ターン終了時に「現在の状態・次の行動」を1行で出力
