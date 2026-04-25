# RULES フレームワーク構築

実施日: 2026-04-25

## 目的

v1 採点後の改善サイクルを自動化するフレームワークを構築。
Scoring → Planning → Implementation → Review → Scoring のループを再現可能にする。

---

## 作成ファイル

| ファイル | 役割 |
|---|---|
| `plan/rules/RULES1_BASIC.md` | 基本ルール・動線・完了条件 |
| `plan/rules/RULES2_PLANNING.md` | 採点結果 → 改善プラン生成 |
| `plan/rules/RULES3_PROGRAMMING.md` | プラン → 実装 |
| `plan/rules/RULES4_REVVUE.md` | 実装 → レビュー (PASS/FAIL) |
| `plan/rules/RULES5_SCORING.md` | 採点・調整後スコア計算 |
| `plan/CURRENT_ITERATION.md` | イテレーション状態管理ハブ |

---

## 動線

```
[初回] CURRENT_ITERATION.md 初期化
     ↓
RULES2 → RULES3 → RULES4 → RULES5
  ↑         ↑        |        |
  |    FAIL差戻し    |    未達なら
  |___________________|___ループ (上限5回)
```

---

## 設計判断

### 完了条件: 調整後スコア 95 点以上

Out-of-scope 項目 (xmf_* 24本、レポート群など) の減点を除いた調整後スコアで判定。
生スコアで 95 点を要求すると Out-of-scope 項目により永久ループが発生するため。

調整後スコア上限は RULES2 の Out-of-scope 宣言時に計算し CURRENT_ITERATION.md に記録。

### CURRENT_ITERATION.md をハブに

「最新ファイルを探す」実装は禁止。全ステップが CURRENT_ITERATION.md を参照して
PLAN/REVIEW/SCORING ファイルのパスを取得する。ファイル参照ミスを構造的に防止。

### RULES4 と RULES5 の役割分離

| | RULES4 レビュー | RULES5 採点 |
|---|---|---|
| 出力 | PASS/FAIL (二値) | 点数 |
| 対象 | 実装の正しさ・バグ・プラン適合 | 計画全体との整合・品質水準 |
| 条件 | FAIL → RULES5 進行禁止 | PASS 確認後のみ実施 |

### 変更ロック (RULES3)

各タスク開始前に変更するファイルの全一覧を宣言。
宣言外ファイルへの Edit/Write は禁止。スコープクリープを構造的に防止。

### レビュー結果を次プランへ引き継ぐ (RULES2)

改善前: RULES2 は採点ファイルのみ参照 → RULES4 の差し戻し項目が消失  
改善後: RULES2 が REVIEW ファイルも読み、未解決問題を「レビュー引き継ぎ項目」として
       プランに強制転記

### 採点基準のコマンド紐付け (RULES5)

主観採点を排除し、コマンドで確認できる項目は全てコマンド結果を根拠にする。

```
ruff check src/ tests/          → コード品質 +25点
grep -r "time\.sleep" src/      → 0件で +10点
grep -n "moneyforward_force_login" src/ → 両ファイルに存在で +15点
```

### イテレーション上限 5 回

5回で未達の場合はユーザーに判断を委ねる。

---

## 改善経緯

初版 RULES → 以下の問題を発見 → 改修:

| 問題 | 改修 |
|---|---|
| 永久ループ (Out-of-scope で 95 点到達不可) | 調整後スコア + 上限計算を追加 |
| ファイル参照ミス (最新ファイルを探す) | CURRENT_ITERATION.md ハブ導入 |
| 採点の再現性なし | コマンド紐付け採点基準 |
| スコープクリープ | 変更ロック追加 |
| RULES4/5 役割重複 | 役割分離を明文化 + FAILガード |
| REVIEW 結果が次プランに未反映 | RULES2 に REVIEW 読取ステップ追加 |
