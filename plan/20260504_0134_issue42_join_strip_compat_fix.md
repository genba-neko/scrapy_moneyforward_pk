# Issue #42: legacy `join_strip` 互換実装 — raw_name 正規化による SK 入力一致

## 経緯

直前 commit (`feat(auth): state filename を可読 mask 形式に変更`) 後、
ユーザーが旧 DynamoDB dump (`.work/results account.csv`) と新 PJ の出力
JSON (`runtime/output/moneyforward_account.json`) を比較する指示を出し、
互換性違反が判明した。

具体的差分 (file:line + 値):

- 新 JSON 出力 (`runtime/output/moneyforward_account.json:1` の record):
  - `account_name`: `"住信SBIネット銀行 Tポイント支店\n(\n\n本サイト\n)\n\n203*******"` (改行混入、`(本サイト)` suffix も trim されず raw)
  - `account_date`: `"2022/12/27\n\n(05/03 17:35)"` (改行混入)
  - `account_status`: `""` (空が多数)
- 旧 DynamoDB CSV (`.work/results account.csv:2-5`):
  - `account_name`: `"nanaco"` / `"オリックス銀行"` 等 (clean、改行なし、trim 済み)
  - `account_date`: `"2022/12/28(05/22 07:16)"` (改行なし、連結)
  - `account_status`: `"正常"` / `"'---"` (値あり)

差分の原因:

- 旧 PJ `mf_account.py:159` は `self.join_strip(...)` を経由して raw_name を抽出
- 旧 PJ `mf_transaction.py:271` の `join_strip`:
  ```python
  text = "".join(texts).replace('\n','').replace('\t','').replace(',','').strip()
  ```
- 新 PJ `_parsers.py:198` (修正前) は `.strip()` のみで `\n` / `\t` / `,` を除去せず
- 結果として:
  - `account_item_key = sha256(raw_name)` の sha256 入力が legacy と異なる
    → SK 値レベルでの互換が崩れる
  - `_ACCOUNT_TRIM_RE = r"^(.+?)\(本サイト\).*"` が `(本サイト)` の前後の改行に
    遮られて trim 失敗 → display 用 `account_name` も raw のまま

## 修正方針

旧 PJ `join_strip` 等価の helper を `_parsers.py` に追加し、`parse_accounts`
の各 field 抽出に適用する。これにより:

- raw_name は legacy 同じ正規化規則 (`\n` / `\t` / `,` 除去 + strip) を経由
- sha256 入力が legacy と同じ規則で生成されるため、SK 値の互換性が
  「同入力 → 同 SK」の意味で成立
- `account_name` (display) の trim regex が再度機能する (`(本サイト)` が
  改行に遮られない)
- `account_amount_number` / `account_date` 等の field も clean になる

## 互換性の限界 (誠実な明文化)

bit-perfect な SK 値の equality を旧 DynamoDB dump と保証することは
できない。理由:

- 旧 fixture (`tests/fixtures/mf_accounts_legacy.html`) と現在の MF 実 HTML
  との間に構造差がある可能性 (ボタン文字、hidden input 数、属性等が増減
  していると `*::text` の集合が変わる)
- 同じ「nanaco」口座でも、legacy 当時の HTML と現在の HTML で td[0] の
  text node 集合が異なれば、join_strip 後の文字列も異なる → sha256 異なる
- 旧 CSV は `account_name` (trim 後) しか保存しないため、当時の raw_name
  (sha256 入力) を直接再構成する手段がない

= **「legacy と同じ正規化規則を使う」ことまでは保証**、**「同じ SK 値が
出る」ことは保証できない**。これは MF 側 HTML 構造が時間で変わる以上、
現実的な達成可能ライン。

### 厳密な意味での「等価性」 (Opus レビュー反映)

新 `_join_strip` の挙動は legacy `join_strip` と **byte-equivalent ではなく
「規則等価 (super-set)」**。

差分:
- 新実装は `texts is None` / `isinstance(texts, str)` のガードを追加。
  None 入力時に空文字を返し、単一 str を 1 要素 list として扱う
- legacy は `list[str]` 入力前提で、None や str を渡すと TypeError を投げる
- 入力が `list[str]` の場合は両者 byte-equivalent
- 入力が None / str の場合のみ動作差 (新は値を返す、legacy は raise)

= 新実装は legacy 出力の super-set。後方互換性を破らない範囲の防御拡張。
本 fix の commit メッセージや plan 内では「規則等価 (super-set)」と表現する。

### `parse_accounts` 全体の legacy 差分 (Opus レビュー反映)

本 fix で adress していない、ただし「legacy と同じ」とは言えない差分:

- **行 skip 条件**: 新 `_parsers.py:193` は `if len(tds) < 4: continue`
  (4 td 未満を skip)、legacy `mf_account.py:155-156` は
  `if not table_row.css("td"): continue` (td が 1 つもない場合のみ skip)
  - 影響: td が 1〜3 個の畸形行で挙動差。新は安全に skip、legacy は
    `tds[1]/tds[2]/tds[3]` の index アクセスで IndexError を起こす可能性
  - 判断: 新の方が defensive で安全 → 意図的に legacy と差を維持
- **account_status の logic**: 新 `_parsers.py:206-213` は CSS の
  `:not(hidden)` filter で span text を join、legacy `mf_account.py:170-174`
  は span loop で id 文字列マッチして last-write-wins
  - 影響: nested span 構造の場合に出力値が異なる (legacy は内側 span の
    text を取得、新は外側の text を取得)
  - 判断: account_status 抽出の root cause は別問題、本 fix 範囲外

これらは「等価性確認の上で意図的に差を残す」項目。本 fix のスコープに
含めない。

## 実装内容

### F1. `_parsers.py` に `_join_strip` 追加

```python
def _join_strip(texts) -> str:
    r"""Mirror legacy ``MfSpider.join_strip`` (mf_transaction.py:271)."""
    if texts is None:
        return ""
    if isinstance(texts, str):
        texts = [texts]
    return (
        "".join(texts)
        .replace("\n", "")
        .replace("\t", "")
        .replace(",", "")
        .strip()
    )
```

### F2. `parse_accounts` の抽出を join_strip 経由に変更

```python
# from
raw_name = "".join(tds[0].css("::text").getall()).strip()
amount_number = "".join(tds[1].css("::text").getall()).strip()
account_date = "".join(tds[2].css("::text").getall()).strip()

# to (legacy mf_account.py:159,165,166 を mirror)
raw_name = _join_strip(tds[0].css("*::text").getall())
amount_number = _join_strip(tds[1].css("*::text").getall())
account_date = _join_strip(tds[2].css("*::text").getall())
```

`*::text` への変更も legacy `mf_account.py:159` に literal に揃えるため。

### F3. 既存 test (`test_parse_accounts_basic` 等) の挙動

- `FIXTURE_HTML` は単純な静的 HTML で `\n` / `\t` / `,` が td 内に
  含まれていないため、修正前後で SK 値は同じ → 既存 assert は変更不要
- `test_parse_accounts_real_legacy` (`tests/test_parsers_legacy_fixtures_unit.py:51`)
  は実 HTML capture を使うため、修正後は SK 値が変わる可能性がある
  (legacy join_strip 規則で正規化された値になる)。assert は「9 件 unique key」
  しか見ていないので影響なし

### F4. 新規 regression test 3 件

`tests/test_account_parse_unit.py` に追加:

- `test_parse_accounts_join_strip_compat_with_legacy`: 改行混入 HTML を input
  に与え、(a) 出力 field に `\n` / `\t` / `,` が残らない, (b) account_name
  が trim regex で正しく trim される, (c) `account_item_key` が 64 char hex,
  を invariant として検証
- `test_join_strip_helper_matches_legacy_rules` (Opus レビュー反映): `_join_strip`
  helper の単体 test。list[str] 入力での legacy 等価動作 + None/str 入力での
  super-set 動作の両方を pin
- `test_parse_accounts_legacy_six_fields_only`: `MoneyforwardAccountItem.fields`
  が legacy の 6 field と一致を pin (login_user 等の追加を regression として
  検出)

## account_status の差分は本 fix の範囲外

新 PJ `_parsers.py:206-213` と legacy `mf_account.py:168-174` の status 抽出
ロジックが異なる (新は CSS の `:not(hidden)` filter + join、legacy は span 走査
ループで last-write-wins)。新出力で status が空文字になる record が多い問題
は別の root cause で、本 fix の `_join_strip` 適用とは独立。本 issue 範囲外
として別途扱う。

## 検証

- `pytest tests/ -v` → 248 件 pass
- `ruff check src/ tests/` → All checks passed
- `pyright src/ tests/` → 0 errors

## 残作業 (本 fix 以後)

- account_status 抽出 logic の legacy 互換化 (本 fix 範囲外、別 issue 候補)
- 旧 DynamoDB dump との実 SK 値比較 (HTML 構造差により非保証、実機 crawl 後
  に sample 比較で目視確認程度)

## 関連

- 本 fix 対象 commit: `feature/42_account_item_key_login_user` 上で本 plan の
  実装後 commit 予定
- 直前 commit (state filename masking): branch 上の HEAD
- 旧 plan `plan/20260503_2005_issue42_compat_noop_revised.md` (compat-first
  no-op 方針)、本 fix はその方針下で「実装によって compat を回復する」位置付け
- audit `plan/20260503_1912_issue42_item_key_audit.md` (旧/新 PJ SK 構成)
- 反省 `plan/20260503_1901_issue42_reflection_recurrence_prevention.md`
  + `plan/20260504_0039_issue42_reflection_recurrence_after_review.md`
