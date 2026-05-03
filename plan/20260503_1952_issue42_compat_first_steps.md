# Issue #42: 互換性優先方針と対応ステップ

ユーザー判断 (2026-05-03): 旧 DynamoDB データとの完全互換を最優先。
account_item_key の SK 値の生成式は legacy と同一形式を維持する。
multi-user の SK 衝突は DynamoDB schema 変更が必要なため、本 issue 範囲外
の別軸課題として保留する。

---

## 確定方針

### account_item_key
- 生成式: `hashlib.sha256(raw_name.encode("utf-8")).hexdigest()` を維持
  (`_parsers.py:201` 現状のまま)
- 値の例: `0046023369873246db3f67380d4692fb4dd0ad2eefb1a47f423f6c943e679798`
- 旧 DynamoDB CSV (`.work/results account.csv:2 行目`) と完全に同一
- → 旧 DynamoDB データと共存・上書き互換
- multi-user の SK 衝突は **既知の制約として残す** (DynamoDB schema 設計時に
  別 issue として扱う)

### login_user の取り扱い
- `MoneyforwardAccountItem` に `login_user` を **新規フィールドとして追加**
- SK には含めない (互換維持のため)
- 出力 JSON / 将来の DynamoDB に「どのユーザーの口座記録か」を残す
- downstream (reports 等) で必要なら `(login_user, account_item_key)` の複合
  キーとして扱える

### state ファイル名 (Issue #43 に関連、ブランチに既に実装済)
- `_hash_user` を `_mask_user` に置換し、
  `{site}_{先頭3字}xxx_{ドメイン先頭3字}xxx_{8文字 hash}.json` 形式
- `.work/作業メモ.txt:5 行目` の指摘 (「認証ステートがわかる名前に」) と
  「emailを直接 leak しない」要件のバランス
- 既にブランチ `feature/42_account_item_key_login_user` に実装済み (revert 対象外)

---

## 対応ステップ

### S1. account_item_key 生成は無変更で確定 (revert 済み、追加変更不要)

- 現状 `_parsers.py:201` は `sha256(raw_name)` のまま
- master と diff なし
- 何もしない

### S2. `MoneyforwardAccountItem` に `login_user` フィールド追加

ファイル: `src/moneyforward_pk/items.py`

```python
class MoneyforwardAccountItem(scrapy.Item):
    year_month_day = scrapy.Field()  # partition key
    account_item_key = scrapy.Field()  # range key (sha256 of name) — legacy compat
    login_user = scrapy.Field()  # multi-user 区別用、SK には含めない (Issue #42)
    account_name = scrapy.Field()
    account_amount_number = scrapy.Field()
    account_date = scrapy.Field()
    account_status = scrapy.Field()
```

### S3. `parse_accounts` のシグネチャ拡張

ファイル: `src/moneyforward_pk/spiders/_parsers.py`

```python
def parse_accounts(
    response: Response,
    login_user: str,
    today: date | None = None,
) -> tuple[list[MoneyforwardAccountItem], bool]:
    ...
    items.append(
        MoneyforwardAccountItem(
            year_month_day=year_month_day,
            account_item_key=account_item_key,  # sha256(raw_name) 不変
            login_user=login_user,                # 新規
            account_name=account_name,
            account_amount_number=amount_number,
            account_date=account_date,
            account_status=account_status,
        )
    )
```

`account_item_key = hashlib.sha256(raw_name.encode("utf-8")).hexdigest()` は
変更しない。`login_user` は Item 格納のみ、key 計算には使わない。

### S4. `account.py` 呼び出し側

ファイル: `src/moneyforward_pk/spiders/account.py`

```python
items, is_updating = parse_accounts(parsed, login_user=self.login_user or "")
```

### S5. テスト更新

ファイル: `tests/test_account_parse_unit.py`

- 既存 3 テストに `login_user="..."` 引数を追加
- `account_item_key` の assert は **legacy 形式 sha256 のまま** (互換確認)
- 新規 assert: `items[0]["login_user"] == "user@example.com"`
- 新規テスト: 同 fixture を 2 user で parse すると `login_user` field は
  異なるが `account_item_key` は同じ (= legacy 通り) ことを確認 (互換性
  regression guard)

ファイル: `tests/test_parsers_legacy_fixtures_unit.py`

- `parse_accounts` 呼び出しに `login_user` 引数追加
- 既存の 9 件 unique key の assert は legacy 形式のまま維持

### S6. ドキュメント

- `CONTRIBUTING.md:86` の SK 説明: `account_item_key` = sha256(name) のまま
  維持で OK (変更不要)
- `src/moneyforward_pk/items.py` のコメント: `# range key (sha256 of name)` の
  脇に「— legacy compat」を追記
- 新 plan ファイル (本ファイル) を Issue #42 「関連資料」にリンク

### S7. multi-user 衝突を既知制約として記録

- 本 plan 内 (本ファイル) に「DynamoDB schema 設計時に別 issue で再検討」を
  明記 (上記「確定方針」に既述)
- 新規 issue を作るかどうかはユーザー判断 (本 plan では新 issue 化しない)

### S8. transaction の同種問題は別 issue 化を提案

`data_table_sortable_value` SK にも login_user 連結なし、multi-user 衝突
可能性あり。本 issue 範囲外。別 issue を立てるかどうかはユーザー判断。
本 plan では着手しない。

### S9. 検証

- `pytest tests/ -v` 全件 pass
- `ruff check src/ tests/` クリーン
- `pyright src/ tests/` クリーン
- ローカル E2E crawl 再実行 (前回の crawl で得られた `account_item_key` の
  日本語混入問題が再発しないこと、`login_user` フィールドが JSON 出力に
  含まれることを確認)

---

## 完了判定

- [ ] S1: account_item_key 生成は無変更 (master 状態確認済み)
- [ ] S2: `MoneyforwardAccountItem` に `login_user` フィールド追加
- [ ] S3: `parse_accounts` シグネチャ拡張
- [ ] S4: `account.py` 呼び出し側更新
- [ ] S5: テスト更新 + multi-user fixture 新規追加
- [ ] S6: ドキュメント更新
- [ ] S7: 本 plan に DynamoDB 移行時の既知制約を文書化 (本ファイル内で完了)
- [ ] S8: transaction 同種問題は本 issue 範囲外と確定 (本ファイル内で確定)
- [ ] S9: pytest/ruff/pyright クリーン + E2E 確認
- [ ] 本 plan を Issue #42 「関連資料」にリンクし issue 本文を更新

---

## ブランチ状態

`feature/42_account_item_key_login_user`:
- account 関連は master 状態 (revert 済み、本 plan の S1)
- session_manager の state filename masking は実装済み (本 plan の S2-S5
  と独立、保持)
- 未 commit、本 plan 反映後にユーザー指示でコミット

---

## 関連

- Issue #42 (本件)
- `plan/20260503_1457_issue42_account_item_key_login_user.md` (旧設計案、
  ASCII canonical 採用方向だったが本方針で破棄)
- `plan/20260503_1912_issue42_item_key_audit.md` (旧/新 PJ の SK 構成
  悉皆調査)
- `plan/20260503_1901_issue42_reflection_recurrence_prevention.md`
  (本件で発生した私の失敗と再発防止)
- Issue #43 (state filename masking、本 plan の masking 実装の元 issue)
- `.work/作業メモ.txt:5 行目` (state ファイル名可読性の元指摘)
- `.work/results account.csv` / `results aset.csv` / `results trans.csv`
  (旧 DynamoDB export、互換性確認の根拠)
