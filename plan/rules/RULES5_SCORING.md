# RULES5_SCORING.md — 採点

scrapy_moneyforward_pk プロジェクトを採点せよ。
採点結果は `plan/YYYYMMDD_HHMM_iter{N}_scoring.md` に保存する。
(例: `plan/20260425_1300_iter1_scoring.md`)

## Step 0: ユーザー指示確認 (必須・最初に実施)

`plan/USER_DIRECTIVES.md` を読む。「設計変更指示」は**採点チェック項目を上書きする**。
- 例: 「DynamoDB 出力をやめて JSON ファイル出力に変更する」→ `DYNAMODB_TABLE` grep チェックを JSON 出力ファイル存在チェックに置き換える
- 「(未設定)」のセクションは無視してよい

## 前提確認 (必須)

1. `plan/CURRENT_ITERATION.md` を読む
   - `current_step` を確認:
     - `initial_scoring` (iteration_count=0 かつ scoring_file 空) → **初回採点モード**: review_status チェックをスキップして採点実施
     - それ以外 → `review_status` が PASS であることを確認。FAIL なら採点禁止・RULES3 へ差し戻し
   - `out_of_scope` と `adjusted_ceilings` を取得 (初回はまだ空 → Out-of-scope は採点後に RULES2 が宣言する)
2. 前回採点ファイル (`previous_scoring_file`) があれば読む → 差分比較用 (初回はなし)

## 事前実行 (必須・全結果を採点に反映)

```bash
cd C:/Users/g/OneDrive/devel/genba-neko@github/scrapy_moneyforward_pk
.venv-win/Scripts/pytest.exe tests/ -v --tb=short
.venv-win/Scripts/ruff.exe check src/ tests/
cd src && ../.venv-win/Scripts/scrapy.exe list
```

---

## 採点カテゴリ (各100点満点)

各カテゴリに「コマンド確認」欄を設ける。コマンドで確認できる項目は**コマンド結果を根拠にせよ**。

### 1. コード品質
**基準**: ruff clean、命名一貫性、責務分離、Twisted/async 統合の正しさ

| コマンド確認 | PASS 条件 | 配点 |
|---|---|---|
| `ruff check src/ tests/` | exit code 0 | +25 |
| `grep -r "time\.sleep" src/` | 0件 | +10 |
| ファイル構造確認 | plan 設計通り | +10 |

残り55点は src/ 全ファイル読取後に加減点。

### 2. テスト品質
**基準**: カバレッジ範囲、テスト独立性、実HTML fixture 有無、CI 連携

| コマンド確認 | PASS 条件 | 配点 |
|---|---|---|
| `pytest tests/ -v` | 全 pass | +20 |
| `pytest --co -q \| grep "test session"` | 件数確認 | +10 |
| `grep -r "setdefault" tests/` | 0件 | +5 |

残り65点は tests/ 全ファイル読取後に加減点。

### 3. 機能移植率
**基準**: 元プロジェクトの全機能カバー率

| コマンド確認 | PASS 条件 | 配点 |
|---|---|---|
| `scrapy list` (src/ 内で実行) | 3スパイダー表示 | +10 |

残り90点は元/リビルド双方のファイル比較で加減点。
**Out-of-scope 調整**: CURRENT_ITERATION.md の `adjusted_ceilings[機能移植率]` を上限とする。

### 4. スパイダー正確性
**基準**: 3本スパイダーのロジックが元コードと同等か、バグなしか

| コマンド確認 | PASS 条件 | 配点 |
|---|---|---|
| `scrapy list` | mf_transaction, mf_asset_allocation, mf_account の3件 | +10 |
| `grep -n "moneyforward_force_login" src/` | middleware と base spider 双方に存在 | +15 |

残り75点は spiders/ + _parsers.py 読取後に加減点。

### 5. セキュリティ
**基準**: 認証情報の扱い、ログへの漏洩リスク、依存ライブラリ

| コマンド確認 | PASS 条件 | 配点 |
|---|---|---|
| `ruff check --select S src/` | 違反 0件 | +20 |
| `.gitignore` に `.env` が含まれる | grep 確認 | +15 |

残り65点は settings.py / base spider 読取後に加減点。

### 6. 運用・CI
**基準**: 自動スケジュール実行、Slack 通知、DynamoDB 書き込み整合、ログ

| コマンド確認 | PASS 条件 | 配点 |
|---|---|---|
| `grep -n "DYNAMODB_TABLE" job_runner.sh` または USER_DIRECTIVES で JSON 出力に変更済なら `grep -n "output_dir\|json" job_runner.sh` | 出力先設定ロジック存在 | +15 |
| `grep -rn "spider_closed" src/` | Slack 通知フック存在 | +10 |
| `.github/workflows/` に schedule トリガー | grep 確認 | +10 |

残り65点は workflows / job_runner 読取後に加減点。
**Out-of-scope 調整**: CURRENT_ITERATION.md の `adjusted_ceilings[運用・CI]` を上限とする。

### 7. 設計・拡張性
**基準**: パートナーポータル拡張容易性、middleware 設計、将来の保守性

| コマンド確認 | PASS 条件 | 配点 |
|---|---|---|
| `grep -n "XMoneyforwardLoginMixin" src/` | mixin 定義が存在 | +10 |
| `grep -rn "managed_page" src/` | context manager 使用 | +10 |

残り80点は moneyforward_base.py / middlewares / pipelines 読取後に加減点。

### 8. ドキュメント
**基準**: README、.env.example、計画書、コメント品質

| コマンド確認 | PASS 条件 | 配点 |
|---|---|---|
| `test -f README.md` | 存在 | +10 |
| `test -f .env.example` | 存在 | +10 |
| `ls plan/*.md` | 計画ファイル存在 | +5 |

残り75点は各ファイル読取後に加減点。

---

## 出力形式

```markdown
### {N}. {カテゴリ名} — **{点数} / 100** (調整後上限: {M}点 / 前回比: +/-X点)
- コマンド確認: {結果} ✓/✗ +{点}
- 加点項目 ✓ +点数
- 減点項目 -点数
```

最後に合計表と調整後スコア表:

```markdown
## スコア集計

| カテゴリ | 点数 | 調整後上限 | 調整後スコア | 前回比 |
|---|---|---|---|---|
| コード品質 | 82 | 100 | 82 | +0 |
| ...

生スコア合計: {X} / 800
調整後合計: {Y} / 調整後上限合計
**完了判定**: 全カテゴリ 調整後スコア 80点以上 かつ Critical 欠陥ゼロ → DONE / 未達 → 次イテレーション
```

---

## 総合評価 (採点後に必ず実施)

### A. 本番投入可否判定
YES/NO で答え、NO の場合はブロッカー (「本番データに影響する」レベルのみ) を列挙。

### B. 致命的欠陥 (Critical Defects)
「このコードを実行したら再現する」レベルのみ。ファイルパス:行番号を明示。

### C. 設計負債の総量評価
半年運用した場合の保守コスト:
- xmf_* 追加工数、HTML変更時の修正箇所数、セッション切れ対応難易度 (1〜5段階)

### D. 元プロジェクト比較
機能・品質・保守性の3軸で 進歩/同等/後退 を判定。

### E. 次イテレーションで着手すべき3件
ROI (工数対点数回復) 最大の3件。推定工数 + 回復見込み点数を添える。

---

## CURRENT_ITERATION.md の更新

採点完了後。`completion_status` は自動ループの次ターン判定に使う:

```yaml
scoring_file: plan/YYYYMMDD_HHMM_iter{N}_scoring.md
scores:
  コード品質: 82
  テスト品質: 63
  機能移植率: 38
  スパイダー正確性: 68
  セキュリティ: 74
  運用CI: 35
  設計拡張性: 79
  ドキュメント: 76
  合計: 515
adjusted_scores:
  機能移植率_ceiling: 60
  運用CI_ceiling: 55
  調整後合計: 570
  調整後上限: 720
# 全カテゴリ調整後スコア >= 80 かつ Critical 欠陥ゼロ → DONE
# iteration_count >= 5 かつ未達 → TIMEOUT
# それ以外 → CONTINUE
completion_status: CONTINUE
```

## 完了時の処理 (completion_status: DONE の場合のみ)

全カテゴリ調整後スコア 95 点以上達成時、以下を順番に実施:

### 1. PR 作成

CURRENT_ITERATION.md の `closed_issues` を全て集約して PR を作成:

```bash
gh pr create \
  --title "improvement: scrapy_moneyforward_pk iter1-{N} quality improvements" \
  --body "$(cat <<'EOF'
## Summary
- 実施イテレーション数: {N}
- 最終スコア: {X} / 800 (調整後: {Y} / {Z})

## Closes
closes #{issue1}, closes #{issue2}, closes #{issue3}

## Changes
- {イテレーション別の主な変更を箇条書き}
EOF
)"
```

### 2. CURRENT_ITERATION.md をリネーム

```bash
mv plan/CURRENT_ITERATION.md plan/YYYYMMDD_HHMM_iteration_log.md
```

### 3. 完了報告

- PR URL
- 完了ファイル名
- 最終スコア (カテゴリ別・調整後合計)
- 実施イテレーション数
- クローズした Issue 一覧

`plan/CURRENT_ITERATION.md` が存在しない状態が次サイクル開始まで正常。

## 制約
- `review_status` が PASS でなければ採点禁止
- ファイル読取・コマンド実行なしの採点は禁止
- コマンドで確認できる項目はコマンド結果を根拠にせよ (主観採点禁止)
- 褒め言葉は根拠なしに書くな。加点した事実のみ記録
- 総合評価は採点の言い換えにしない — 採点で出なかった観点を出せ
