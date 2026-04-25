# scrapy_moneyforward_pk 自動改善ループ — 使い方

## 起動

```
/loop plan/rules/RULES0_LOOP.md を読み、指示に従って1ステップ実行せよ
```

`/loop` は毎ターン同じプロンプトを再実行する仕組み。引数でRULES0を指定する必要がある。
RULES0 が `CURRENT_ITERATION.md` を読んで次ステップを自動選択する。

---

## フロー

```
初回起動
  → RULES5: 現状採点 (初回スコア)
  → RULES2: 改善プラン作成 + GitHub Issue 作成
  → RULES3: 実装・コミット (closes #N)
  → RULES4: レビュー (PASS/FAIL)
  → RULES5: 再採点・スコア更新
  → 基準達成? → DONE (PR作成) / 未達 → 次イテレーション
```

停止条件:
- 全カテゴリ 調整後スコア ≥ 95 → **DONE** + PR 自動作成
- 5イテレーション消化 → **TIMEOUT** + サマリー出力

---

## 人間の介入ポイント

### 設計指示を入れたいとき

`plan/USER_DIRECTIVES.md` を編集する。次の RULES2 ステップで自動反映。

```markdown
## 設計変更指示 (実装に反映せよ)
- DynamoDB 出力をやめて JSON ファイル出力に変更する
- Python 3.12 以上を前提にする
```

採点基準より **USER_DIRECTIVES.md が優先**される。

### 完了後 (DONE)

PR が自動作成済み → 人間がレビュー・マージ。
`CURRENT_ITERATION.md` は `plan/YYYYMMDD_HHMM_iteration_log.md` にリネーム済み。

---

## 次キャンペーン

DONE / TIMEOUT 後に再度同じコマンドで `/loop` を実行するだけ。
`CURRENT_ITERATION.md` がなければテンプレから自動コピーして新キャンペーン開始。

---

## ファイル構成

| ファイル | 役割 |
|---|---|
| `RULES0_LOOP.md` | ステートマシン オーケストレーター |
| `RULES1_BASIC.md` | 基本ルール・完了条件 |
| `RULES2_PLANNING.md` | 採点+指示 → 改善プラン生成 |
| `RULES3_PROGRAMMING.md` | プラン → 実装・コミット |
| `RULES4_REVVUE.md` | 実装 → PASS/FAIL レビュー |
| `RULES5_SCORING.md` | 採点・完了判定 |
| `CURRENT_ITERATION_TEMPLATE.md` | 新キャンペーン用テンプレ |
| `../CURRENT_ITERATION.md` | イテレーション状態ハブ (ライブ) |
| `../USER_DIRECTIVES.md` | ユーザー指示書 |
