# Issue #42: 改訂版 — compat-first 下では「コード無変更 + 文書追記 + scope 分割」

Codex / Opus の独立レビュー (両者一致) を受けて、`plan/20260503_1952_issue42_compat_first_steps.md`
の S2 (login_user フィールド追加) を撤回し、本 issue の deliverable を
再定義した改訂版。

---

## レビューで明らかになった誤り (R-1, R-3, R-4 違反の自己確認)

旧 plan (1952 版) で私が S2 として提案した
`MoneyforwardAccountItem` への `login_user` フィールド追加は、Codex / Opus 両者から **scope creep / compat-first 方針違反** と判定された。

### Item 構造の事実 (file:line + 値)

- 旧 PJ `scrapy_moneyforward/src/moneyforward/items.py:46-54`: 6 フィールド
  ```python
  year_month_day, account_item_key, account_name,
  account_amount_number, account_date, account_status
  ```
- 旧 DynamoDB export `.work/results account.csv:1` ヘッダ: 6 列 (上記と一致)
- 新 PJ `src/moneyforward_pk/items.py:44-52` (master 状態): 6 フィールド (上記と一致)

→ 完全互換 = **6 フィールド維持**。`login_user` を加えると `MoneyforwardAccountItem` の attribute 集合が legacy の superset になり、対称的な互換ではなくなる。
DynamoDB は schemaless なので「保存可能」ではあるが、それは「互換」ではない。

### login_user 追加の根拠不足

- downstream consumer 不在: `audit` plan で「現 PJ 内で `account_item_key` の consumer なし」「`MoneyforwardAccountItem` の field を消費する場所なし」と既に確認済み
- `login_user` を Item に追加しても、それを読む場所が現状ゼロ → YAGNI 違反
- 旧 plan (1952) の S2 説明に file:line 出典・具体値・consumer の引用なし → 自己反省 plan の R-1, R-3 違反

### 反省 plan が次の plan に効いていない構造的問題

私が `plan/20260503_1901_issue42_reflection_recurrence_prevention.md` で書いた
R-1〜R-10 を、その次に書いた 1952 版で守れていない。Opus reviewer の指摘:
「reflection が次生成に効いていない F-項目の root cause がそのまま残存」。

---

## 確定方針 (改訂)

Issue #42 は compat-first 方針下では「multi-user 衝突を解決する issue」ではなく、
「**解決には schema/key 非互換が必要なので今回は legacy 互換を維持して保留する issue**」
に再定義する。本 issue の deliverable は以下:

1. legacy 互換が保たれていることの **regression test 追加**
2. multi-user 衝突を **既知制約として明文化**
3. transaction の同種問題を **別 issue として正式に切り出し**
4. state filename masking 作業を **Issue #43 系の別 branch / PR に分離**
5. Issue #42 ブランチ名と実態の乖離を整理

**コード変更は account 関連には一切ない**。

---

## 改訂後 対応ステップ

### S1. legacy 互換 regression test 追加

ファイル: `tests/test_account_parse_unit.py` (新規 test 追加)

```python
def test_account_item_key_matches_legacy_sha256_format():
    """Issue #42 compat-first: account_item_key は legacy `sha256(raw_name)` で
    64 文字 hex 形式を維持する。旧 DynamoDB export と key 値互換。
    """
    response = make_response(FIXTURE_HTML)
    items, _ = parse_accounts(response, today=date(2025, 1, 15))
    expected_key = hashlib.sha256(
        "みずほ銀行(本サイト)追記".encode("utf-8")
    ).hexdigest()
    assert items[0]["account_item_key"] == expected_key
    assert len(items[0]["account_item_key"]) == 64
    assert all(c in "0123456789abcdef" for c in items[0]["account_item_key"])

def test_account_item_has_legacy_six_fields_only():
    """Issue #42 compat-first: MoneyforwardAccountItem は legacy 6 フィールドの
    まま、追加 attribute なし。
    """
    expected = {
        "year_month_day", "account_item_key", "account_name",
        "account_amount_number", "account_date", "account_status",
    }
    assert set(MoneyforwardAccountItem.fields.keys()) == expected
```

(既存テストは `account_item_key` が sha256 形式であることを既に検証している
ので、上記 2 件を補強として追加。)

### S2. legacy CSV 整合 regression (任意、参考データに依存)

旧 DynamoDB export `.work/results account.csv:2` の値
`0046023369873246db3f67380d4692fb4dd0ad2eefb1a47f423f6c943e679798` は
特定 user の特定 raw_name の sha256 結果。これと一致する fixture を作るのは
過剰なので、本 issue 範囲では実施しない (header column の一致のみ S1 で確認)。

### S3. multi-user 衝突を既知制約として明文化

ファイル: `CONTRIBUTING.md` (該当節への追記)
ファイル: `plan/rules/RULES3_PROGRAMMING.md` (DynamoDB 変更禁止キー節への追記)

追記内容:
- `account` の SK は legacy `sha256(raw_name)` 形式で、login_user を含まない
- multi-user 環境では同 (year_month_day, sha256(raw_name)) で異 user の record が衝突する
- これは旧 PJ から継承した既知制約で、解決には DynamoDB schema 変更が必要
- 別 issue (Issue #44 候補、本 plan で draft) で扱う

### S4. transaction 同種問題の別 issue ドラフト

新規 issue draft (本 plan に本文を記載、ユーザーが確定/作成):

- 表題案: `feat: transaction SK / account SK の multi-user 対応 (DynamoDB schema 再設計)`
- 内容:
  - transaction SK = `data_table_sortable_value` のみ、login_user なし
  - account SK = `sha256(raw_name)`、login_user なし
  - 両者とも同 PK + 同 SK で multi-user の record が衝突
  - 解決には schema 変更 (PK or SK に login_user を含める) が必要
  - Issue #42 で legacy 互換を最優先したため本問題は分離
  - DynamoDB 層連携実装と一緒に再検討

### S5. state filename masking を別 branch / PR に分離

現状 branch `feature/42_account_item_key_login_user` には:
- `src/moneyforward_pk/auth/session_manager.py` (`_hash_user` → `_mask_user` 置換)
- `tests/test_session_manager_unit.py` (上記対応テスト)

の変更が残っている。これらは Issue #43 (Playwright session 永続化) の派生問題で、
本 issue (#42) の compat 議論とは独立。

提案:
1. 現 branch の masking 変更を別 branch (例: `feature/43_state_filename_masked`) に
   cherry-pick または revert+新規実装
2. Issue #43 系 PR として個別レビュー・マージ
3. Issue #42 の本 PR は account-related の **無変更状態 + 文書追記** のみ

具体手順は破壊的操作を含むため、ユーザー指示後に実行。

### S6. ブランチ名の整理

`feature/42_account_item_key_login_user` は当初の方針 (account_item_key を
`{spider}-{login_user}-{...}` に変更) を反映した名前だが、改訂後は account
関連を一切変更しない方針なので名前と実態が乖離する。

選択肢:
- (a) ブランチ名そのままで本 plan の deliverable (test + 文書) を commit
- (b) 改名: `chore/42_compat_audit_only` 等
- (c) ブランチ破棄 + master に直接 test + docs を commit

どれを取るかはユーザー判断。

### S7. Issue #42 本文更新

GitHub Issue #42 の本文を改訂後 deliverable に合わせて更新:
- 「multi-user SK 衝突解決」ではなく
- 「legacy 互換確認 + 既知制約文書化 + multi-user 解決は別 issue 分離」

---

## 改訂前後の差分 (旧 1952 plan からの変更)

| 項目 | 旧 1952 plan | 本改訂 plan |
|---|---|---|
| `account_item_key` 生成式 | sha256 維持 | sha256 維持 (同) |
| `MoneyforwardAccountItem` フィールド | 7 (login_user 追加) | **6 (legacy 通り、追加なし)** |
| `parse_accounts` シグネチャ | login_user 追加 | **無変更** |
| `account.py` 呼び出し側 | login_user 渡し | **無変更** |
| テスト | login_user assert 追加 | **6 フィールド維持 + sha256 形式の regression test** |
| ドキュメント | login_user コメント | **legacy 互換明記 + multi-user 既知制約明文化** |
| transaction 同種問題 | 「ユーザー判断」に丸投げ | **本 plan で issue draft 提示** |
| state masking | branch に残置 | **別 branch / PR に分離** |
| ブランチ名 | そのまま | **ユーザー判断 (改名 or 維持)** |

---

## 完了判定

- [ ] S1: legacy 互換 regression test 2 件追加 + pytest pass
- [ ] S3: CONTRIBUTING.md / RULES3_PROGRAMMING.md に既知制約明文化
- [ ] S4: 別 issue draft 本文 (本 plan に記載済み) をユーザー承認後 GitHub に登録
- [ ] S5: state masking 変更を別 branch に分離 (ユーザー指示後に実行)
- [ ] S6: ブランチ名整理 (ユーザー判断後)
- [ ] S7: Issue #42 本文更新

---

## ブランチ状態

`feature/42_account_item_key_login_user`:
- account 関連: master 状態 (revert 済み、改訂後も無変更維持)
- session_manager の state filename masking: 実装済み (本 plan で別 branch
  に分離予定)
- 未 commit、本 plan 反映後にユーザー指示でコミット または revert

---

## 関連

- Issue #42 (本件)
- 旧 plan: `plan/20260503_1457_issue42_account_item_key_login_user.md` (ASCII canonical 採用案、破棄)
- 旧 plan: `plan/20260503_1952_issue42_compat_first_steps.md` (login_user フィールド追加案、本改訂で撤回)
- audit: `plan/20260503_1912_issue42_item_key_audit.md` (旧/新 PJ の SK 構成 悉皆調査)
- reflection: `plan/20260503_1901_issue42_reflection_recurrence_prevention.md` (R-1〜R-10、本 plan で遵守)
- Issue #43 (state filename masking、別 branch に分離予定)
- `.work/results account.csv` / `results aset.csv` / `results trans.csv` (旧 DynamoDB export、互換性確認の根拠)
- Codex / Opus 独立レビュー (本改訂の根拠)
