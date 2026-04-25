# RULES2_PLANNING.md — 改善プランナー

scrapy_moneyforward_pk 改善プランを立てよ。

## プロジェクトパス
- 元: `C:/Users/g/OneDrive/devel/genba-neko@github/scrapy_moneyforward`
- リビルド: `C:/Users/g/OneDrive/devel/genba-neko@github/scrapy_moneyforward_pk`

## 事前読取 (必須・この順で読め)

### Step 0: ユーザー指示の確認
`plan/USER_DIRECTIVES.md` を読む。
- 「設計変更指示」はプランのタスクより**最優先**で反映する
- 「スコープ変更」は Out-of-scope / In-scope の判定を上書きする
- 「優先度の上書き」はタスク順序に反映する
- 「(未設定)」のセクションは無視してよい

### Step 1: イテレーション状態の確認
`plan/CURRENT_ITERATION.md` を読む。
- なければ `plan/CURRENT_ITERATION.md` を初期テンプレートから新規作成してから続行
- `iteration_count` が 5 以上ならユーザーに報告して停止せよ (無限ループ防止)

### Step 2: 前回レビュー結果の取り込み
CURRENT_ITERATION.md の `review_file` に記載されたファイルを読む。
- FAIL 判定なら未解決の問題点を全て次プランに引き継ぐ (RULES4 の差し戻し項目)
- PASS または初回なら省略

### Step 3: 前回採点結果の取り込み
CURRENT_ITERATION.md の `scoring_file` に記載されたファイルを読む。
- なければ採点を先に実施してから戻れ (RULES5_SCORING.md 参照)
- 各カテゴリの減点項目を全て抽出する

## プラン作成ルール

### スコープ判定
採点の減点項目 + レビューの未解決問題を全列挙し分類:

- **In-scope**: 単独完結・外部依存なし・本番環境不要
- **Out-of-scope**: MoneyForward 実環境必須 / 別 PJ 依存 / 明示スコープ外

Out-of-scope は理由を1行で記録して無視。**カテゴリ別の調整後スコア上限も計算せよ**:

```
調整後上限 = 100 - (そのカテゴリの Out-of-scope 減点合計)
例: 機能移植率の Out-of-scope 減点が -40点なら 調整後上限 = 60点
```

### タスク分解ルール
- 1タスク = 1 PR で完結できる粒度
- 複数ファイル跨ぎでも論理的に一体なら 1 タスク
- タスク数は最大 10 件。優先度低いものは「将来課題」に1行記録
- 依存関係があるなら順序を明示
- **1イテレーションの実装タスク上限 = 5 件** (文脈窓制限。残りは次イテレーションへ)

### 優先度・ROI

| 項目 | 内容 |
|---|---|
| Priority | P1=本番ブロッカー / P2=スコア回復高 / P3=品質改善 |
| 工数 | S=~1h / M=~3h / L=~8h |
| 回復点 | 改善見込み点数合計 |
| ROI | 回復点 / 工数係数 (S=1, M=3, L=8) |

P1 を先頭固定。P2 は ROI 降順。P3 は末尾。

## 出力ファイル

保存先: `plan/YYYYMMDD_HHMM_iter{N}_plan.md`
(例: `plan/20260425_1030_iter1_plan.md`)

```markdown
# scrapy_moneyforward_pk 改善プラン

作成: {日時}
イテレーション: {N}回目
ベース採点: {SCORING ファイル名}
ベースレビュー: {REVIEW ファイル名 / なし}
現在合計: {X} / 800　調整後目標: {Y} / 800

## Out-of-scope と調整後スコア上限
| カテゴリ | Out-of-scope 減点 | 調整後上限 |
|---|---|---|
| 機能移植率 | -40 | 60 |

## レビュー引き継ぎ項目 (前回 FAIL の未解決問題)
- {問題}: {ファイルパス:行番号}

## Issue グループ (1イテレーション = 2〜4 Issue)

タスクを論理的なまとまりでグループ化し、1グループ = 1 Issue とする。
細かく切りすぎない: 同カテゴリ・同依存チェーン・同ファイル群は1 Issue にまとめる。

| Issue | タイトル | 対象タスク | Priority |
|---|---|---|---|
| #- | {論理グループ名} | T1, T2 | P1 |
| #- | {論理グループ名} | T3 | P2 |

Issue 作成コマンド (プラン保存後に実行):
```bash
gh issue create --title "{タイトル}" --body "{問題の概要・対象ファイル}"
# → 発行された Issue 番号を CURRENT_ITERATION.md の open_issues に記録
```

## タスク一覧 (今イテレーション: 最大5件)

| # | タイトル | Issue | Priority | 工数 | 回復点 | ROI | 依存 |
|---|---|---|---|---|---|---|---|
| T1 | ... | #12 | P1 | S | +20 | 20.0 | なし |

## タスク詳細

### T{N}: {タイトル} (Issue #{M})
**Priority**: P{N}  **工数**: S/M/L  **回復見込**: +{X}点 ({カテゴリ})  **依存**: T{M}/なし

**問題**: {採点/レビューの指摘内容 1〜2行。ファイルパス:行番号含む}

**実装方針**: {何をどう変えるか。擬似コード or 箇条書き。コード全文不要}

**変更ロック** (このタスクで変更するファイルの全一覧):
- `src/...`
- `tests/...`

**完了判定**:
- [ ] {検証コマンド or 確認手順}
- [ ] ruff clean 維持
- [ ] pytest 全 pass 維持

## 実施順序

T1 → T2 → T4
T3 (独立)

## 将来課題 (今イテレーション対象外)
- {項目}: {理由}
```

## CURRENT_ITERATION.md の更新

プラン保存・Issue 作成後:
```yaml
iteration_count: N+1
plan_file: plan/YYYYMMDD_HHMM_iter{N}_plan.md
review_file: ""                    # 新イテレーション開始でリセット
previous_scoring_file: {読んだ scoring_file の値}  # 前回比較用に保持
scoring_file: ""                   # クリア → RULES0 の RULES5 実行判定がシンプルになる
review_status: ""                  # リセット
review_fail_count: 0               # リセット
programming_status: ""             # リセット
review_blockers: []                # リセット
completed_tasks: []                # リセット
skipped_tasks: []                  # リセット
open_issues: [12, 13]              # gh issue create で発行された番号
# out_of_scope / adjusted_ceilings / closed_issues は引き継ぐ
```

## 制約

- 実装コード書くな — 方針と変更箇所だけ
- 採点で加点された良い箇所は変えるな
- プラン保存後、保存パスと CURRENT_ITERATION.md 更新完了を出力せよ
