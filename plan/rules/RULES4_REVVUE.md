# RULES4_REVVUE.md — レビュー

## 役割の明確化

**RULES4 = 実装の正しさを検証する関門 (PASS/FAIL の二値)**
- バグ・テスト欠落・プラン適合を確認する
- 点数はつけない (採点は RULES5 の仕事)
- **FAIL のまま RULES5 に進むことは絶対禁止**

## Step 0: ユーザー指示確認 (必須・最初に実施)

`plan/USER_DIRECTIVES.md` を読む。「設計変更指示」に記載された内容は**レビュー観点を上書きする**。
- 例: 「DynamoDB 出力をやめて JSON ファイル出力に変更する」→ Section E の DynamoDB キー互換チェックを JSON 出力互換チェックに置き換える
- 「(未設定)」のセクションは無視してよい

## 事前実行 (必須・結果をレビューに反映)

```bash
cd C:/Users/g/OneDrive/devel/genba-neko@github/scrapy_moneyforward_pk
.venv-win/Scripts/pytest.exe tests/ -v --tb=short
.venv-win/Scripts/ruff.exe check src/ tests/
cd src && ../.venv-win/Scripts/scrapy.exe list
```

## 事前読取

1. `plan/CURRENT_ITERATION.md` を読む → `plan_file` を取得
2. そのプランファイルを読む (タスク一覧・完了判定・変更ロック を確認)
3. 各タスクの「変更ロック」に記載されたファイルのみ読む

## レビュー観点

### A. 事前チェック (自動判定)
| 項目 | PASS 条件 |
|---|---|
| pytest | 全 pass (1件でも FAIL → RULES4 FAIL) |
| ruff | exit code 0 (違反あり → RULES4 FAIL) |
| scrapy list | 3スパイダー表示 (欠ければ FAIL) |

### B. プラン適合確認
- 各タスクの完了判定チェックボックスが全て `[x]` か
- 変更ロック外のファイルが変更されていないか (`git diff --name-only` で確認)
- 未完了タスクがあれば FAIL、RULES3 へ差し戻す

### C. バグ・ロジックエラー
ファイルパスと行番号を必ず記載。

重点確認項目:
- セッション切れ → 再ログイン が正しく配線されているか
- DynamoDB テーブル切替ロジックが spider 別に動くか
- parser の CSS/XPath セレクタが実装意図と一致するか (`ancestor::` vs `parent::` 等)
- Twisted reactor 上の `time.sleep` がないか
- `managed_page` の close が二重に呼ばれていないか

### D. テスト品質
- 追加実装に対してテストが追加されているか
- 境界条件 (空リスト、None、セッション切れ) をカバーしているか
- `conftest.py` の env 注入が `monkeypatch.setenv` か (`setdefault` は禁止)

### E. 元プロジェクト互換性
**USER_DIRECTIVES.md の設計変更指示を優先する。指示で上書きされた項目はその指示に沿って検証せよ。**
- DynamoDB キー名が変わっていないか: `year_month`, `data_table_sortable_value`, `asset_item_key`
  *(USER_DIRECTIVES に「DynamoDB → JSON 出力」指示がある場合: JSON ファイルの同等キー存在を代わりに確認)*
- Item フィールド名が追加・削除・改名されていないか

## 出力ファイル

保存先: `plan/YYYYMMDD_HHMM_iter{N}_review.md`
(例: `plan/20260425_1200_iter1_review.md`)

```markdown
# レビュー結果

日時: {日時}
イテレーション: {N}回目
対象プラン: {PLAN ファイル名}
実施タスク: T1, T2, T3

## A. 事前チェック
- pytest: {N}/{N} pass
- ruff: clean
- scrapy list: mf_account, mf_asset_allocation, mf_transaction

## B. プラン適合
- [x] T1 完了判定済み
- [ ] T2 完了判定 未チェック → **差し戻し理由**

## C. バグ・ロジックエラー

### Critical (本番障害レベル)
- `src/foo.py:42`: {問題}

### Major (データ不整合レベル)
- `src/bar.py:10`: {問題}

### Minor (品質問題)
- `src/baz.py:5`: {問題}

## D. テスト品質
{問題あれば列挙。なければ「問題なし」}

## E. 元プロジェクト互換性
{問題あれば列挙。なければ「問題なし」}

## 判定: PASS / FAIL

### PASS の場合
→ RULES5_SCORING.md へ進む

### FAIL の場合
→ **RULES5 への進行禁止**
→ RULES3 に差し戻す。修正必須項目:
- {項目}: {ファイルパス:行番号}
```

## 判定基準

| 判定 | 条件 |
|---|---|
| PASS | 事前チェック全通過 / Critical なし / プラン適合 |
| FAIL | いずれか1つでも未達 |

Major/Minor のみなら PASS でよい。ただしレポートに明記し次プランで対処。

## CURRENT_ITERATION.md の更新

レビュー完了後。`review_blockers` は自動化ループが RULES3 再実行時に読む機械可読形式で記録:

```yaml
review_file: plan/YYYYMMDD_HHMM_iter{N}_review.md
review_status: PASS   # または FAIL
review_blockers:
  - file: src/moneyforward_pk/middlewares/playwright_session.py
    line: 54
    issue: "request.copy() 後に playwright_page を pop していない"
    fix: "new_req.meta.pop('playwright_page', None) を copy() 直後に追加"
  - file: src/moneyforward_pk/spiders/base/moneyforward_base.py
    line: 90
    issue: "force_login フラグの処理がない"
    fix: "start() 内で meta.get('moneyforward_force_login') を確認して login_flow を呼ぶ"
```

PASS の場合: `review_blockers: []`

## 制約

- ファイル読取なしのレビューは禁止
- 問題なしの場合も「問題なし」と明示して全セクションを埋めること (省略禁止)
- 採点 (点数付け) はするな — それは RULES5 の仕事
