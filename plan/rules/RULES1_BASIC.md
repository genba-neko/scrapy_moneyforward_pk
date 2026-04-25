# RULES1_BASIC.md — 基本ルール

## プロジェクト概要

scrapy_moneyforward (Scrapy + Splash + Lua) を scrapy_moneyforward_pk (Scrapy + Playwright) へ再構築。
設計仕様: `plan/20260425_0438_rebuild_scrapy_moneyforward.md`

| 項目 | パス |
|---|---|
| 元プロジェクト | `C:/Users/g/OneDrive/devel/genba-neko@github/scrapy_moneyforward` |
| リビルド | `C:/Users/g/OneDrive/devel/genba-neko@github/scrapy_moneyforward_pk` |
| 参考構造 | `C:/Users/g/OneDrive/devel/genba-neko@github/scrapy_smbcnikko_pk` |
| イテレーション管理 | `plan/CURRENT_ITERATION.md` |

## 実施動線

### 自動モード (推奨)
`/loop` で `plan/rules/RULES0_LOOP.md` を実行。
CURRENT_ITERATION.md の状態を読んで RULES2→3→4→5 を自動でループ。

### 手動モード
```
[初回のみ] plan/CURRENT_ITERATION.md を初期化
     ↓
RULES2_PLANNING → RULES3_PROGRAMMING → RULES4_REVVUE → RULES5_SCORING
       ↑                                    |                  |
       |                              FAIL: 差し戻し     調整後スコア未達
       |___________________________________________________|
                      次イテレーション (上限5回)
```

1. **RULES0_LOOP.md** — 自動オーケストレーター (ステートマシン)
2. **RULES2_PLANNING.md** — 採点結果を読んで改善タスクをプラン化
3. **RULES3_PROGRAMMING.md** — プランに従って実装、エラーはスキップ+記録
4. **RULES4_REVVUE.md** — PASS/FAIL 判定、FAIL 項目を機械可読形式で記録
5. **RULES5_SCORING.md** — 採点、completion_status を自動設定

## 完了条件

RULES5 の採点で **In-scope 項目を反映した調整後スコアが全カテゴリ 95 点以上**。

- 調整後スコアの計算方法は RULES5 参照
- Out-of-scope 項目 (xmf_*、レポート群 など) による減点は調整後スコアから除外
- **イテレーション上限: 5回**。5回で未達の場合はユーザーに報告して判断を仰ぐ

## CURRENT_ITERATION.md の管理

`plan/CURRENT_ITERATION.md` は全ステップが参照する唯一のイテレーション状態ファイル。
場所は常に `plan/CURRENT_ITERATION.md` 固定。

- **初回**: RULES2 実施前に `plan/CURRENT_ITERATION.md` を作成 (テンプレートは `plan/CURRENT_ITERATION.md` 参照)
- **各ステップ**: 自分のステップ完了後に対応フィールドを更新してから次へ進む
- 「最新の SCORING/PLAN/REVIEW ファイルを探す」という実装は禁止。必ずここを読む

### 完了時のリネーム (RULES5 が担当)

全イテレーション完了 (`completion_status: DONE`) 後、RULES5 が以下を実施:

```
plan/CURRENT_ITERATION.md
  → plan/YYYYMMDD_HHMM_iteration_log.md  (完了日時・既存ファイルと同じ命名規則)
```

リネーム後は `plan/CURRENT_ITERATION.md` が存在しない状態が正常。
次サイクル開始時に RULES2 が再作成する。

## 共通制約 (全 RULES で適用)

- **言語**: 日本語・原始人モード (体言止め、助詞省略、冗長語削除)
- **ファイル読取**: ツール実行・ファイル読取なしの判断禁止
- **テスト**: `pytest tests/ -v` は各実装後に必ず実行、全 pass 維持
- **Lint**: `ruff check src/ tests/` clean 維持、違反を新規導入しない
- **コミット**: タスク完了ごとに実施 (pytest pass + ruff clean 確認後)。詳細は RULES3 参照
- **採点比較**: 前回採点ファイルが `plan/` にあれば差分を「前回比 +/-N点」で付ける
- **計画ファイル命名**: `plan/YYYYMMDD_HHMM_iter{N}_{種別}.md`
  - プラン: `_plan` / レビュー: `_review` / 採点: `_scoring`
  - 例: `20260425_1030_iter1_plan.md`, `20260425_1200_iter1_review.md`
  - イテレーション番号で全ファイルが紐づく
- **CURRENT_ITERATION.md**: 状態ハブ (ファイルポインタ・ステータス・スコア)。plan/ ファイルが人間が読む記録、CURRENT_ITERATION.md がエージェントが参照する機械可読状態
