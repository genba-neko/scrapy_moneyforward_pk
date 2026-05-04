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

### Unit / static check

- `pytest tests/ -v` → 249 件 pass (新規 +3)
- `ruff check src/ tests/` → All checks passed
- `pyright src/ tests/` → 0 errors

### E2E 検証 (本 fix commit 後の crawl_runner 実行結果)

実行: `crawl_runner` 経由 18 invocation 全成功 (Total invocations: 18,
Succeeded: 18, Failed: 0, Elapsed: 472.2s)。

`runtime/output/moneyforward_account.json` を `.work/results account.csv`
の legacy 互換要件と照合:

| invariant | 結果 |
|---|---|
| records 数 | 39 / 39 unique key |
| field 集合 | `{year_month_day, account_item_key, account_name, account_amount_number, account_date, account_status}` = legacy 6 フィールド完全一致 |
| `account_name` 改行混入 | 0 / 39 (修正前は全件混入) |
| `account_name` `(本サイト)` suffix 残存 | 0 / 39 (trim 正常動作) |
| `account_amount_number` 改行混入 | 0 / 39 |
| `account_amount_number` カンマ残存 | 0 / 39 (`12,345円` → `12345円`) |
| `account_date` 改行混入 | 0 / 39 (`2022/12/27\n\n(05/03 17:35)` → `2022/12/27(05/04 00:56)`) |
| `account_item_key` 64-hex 形式 | 39 / 39 (legacy SK shape 完全一致) |

サンプル `account_name` 例: `住信SBIネット銀行 Tポイント支店` 等、
legacy CSV (`nanaco` / `オリックス銀行`) と同じく改行・カンマ・suffix なし。

→ **legacy 互換規則 (`\n` / `\t` / `,` 除去 + `(本サイト)` 以降の trim) を
両方とも満たすクリーン出力**。bit-perfect な SK 値の equality は HTML 構造
変動の可能性があるため非保証だが、規則 compat は完全達成。

### 他 spider 出力の compat 検証 (本 fix の影響なし側)

#### transaction (`runtime/output/moneyforward_transaction.json` vs `.work/results trans.csv`)

| 観点 | 旧 CSV | 新 JSON | 一致 |
|---|---|---|---|
| record 数 | 50 | 274 (今回 crawl 範囲) | — |
| field 集合 | 16 fields | 同 16 | ✓ |
| SK format `\d{4}/\d{2}/\d{2}-\d+` | 50/50 | 274/274 | ✓ |
| year_month format `\d{6}` | 50/50 | 274/274 | ✓ |
| (year_month, SK) duplicate | 0 | 0 | ✓ |

注: SK 単独で 29 件の duplicate あり (105 unique vs 274 records)。これは
MF 仕様で同じ取引が複数月ビューに現れる (例: 振替予定 `2025/08/31-1758540136636743858`
が 202509-202602 の 6 月分に出現)。`(year_month, SK)` 複合 key では衝突なし、
DynamoDB compat 問題なし。

seq 部の桁数は時系列で変動 (旧 12 桁 0-padding、新 19 桁 padding なし)
だが、グローバル一意性は維持。

#### asset_allocation (`runtime/output/moneyforward_asset_allocation.json` vs `.work/results aset.csv`)

| 観点 | 旧 CSV | 新 JSON | 一致 |
|---|---|---|---|
| record 数 | 50 | 18 (今回 crawl 範囲) | — |
| field 集合 | 10 fields | 同 10 | ✓ |
| SK format `{spider}-{login_user}-portfolio_det_*` | 50/50 | 18/18 | ✓ |
| (PK, SK) duplicate | 0 | 0 | ✓ |

#### state filename (`runtime/state/`)

- 6 ファイル全て新 mask 形式 (`{site}_{先頭3字}xxx_{ドメイン先頭3字}xxx_{8文字hash}.json`)
- legacy hash 形式 (`{site}_[0-9a-f]{12}.json`) は 0 件 (掃除済み)

### 検出された問題 (本 fix 範囲外)

#### account_status の空文字問題

新 `runtime/output/moneyforward_account.json` の 39 records のうち
`account_status` 別の分布:

- `""` (空文字): 29 件 (74%)
- `"正常"`: 9 件 (23%)
- `"現在メンテナンス中です。今しばらくお待ち下さい。"`: 1 件 (3%)

旧 PJ CSV (`.work/results account.csv` の `account_status` 列) は
`"正常"` / `"'---"` 等の値を持つ。

**重要な訂正 (ユーザー指摘反映)**: `"'---"` (Excel safety prefix 付きの
`---`) は **MF HTML から取得した値ではなく、legacy code 側の hardcoded
fallback**。

旧 PJ `mf_account.py:169` の実装:

```python
account_status = "---"  # loop 前に初期化 (hardcoded fallback)
for status_span in table_row.css("td")[3].css('span'):
    status_id = status_span.xpath('@id').get()
    status_text = self.join_strip(status_span.css('span::text').get())
    if 'js-status-sentence-span-' in status_id:
        account_status = status_text  # マッチ時のみ上書き
```

= マッチする span が見つからない / span text が空の場合は `"---"` のまま。
旧 CSV の `"'---"` はこの default 値の出現で、「scraping で常に値が
取れていた」わけではない。

新 PJ `_parsers.py:213` には fallback がないため、空文字になる。

原因の見立て (Opus レビューでも指摘済):
- 新 PJ `_parsers.py:206-213` は CSS の `:not([id^="js-hidden-status-sentence-span"])`
  filter で span text を **直接取得** (外側 span の text のみ)
- 旧 PJ `mf_account.py:168-174` は td[3] 内の全 span を loop し、id 文字列
  マッチで `status_span.css('span::text').get()` (= **入れ子 span** の text)
  を取得 (last-write-wins)
- 実 MF HTML が `<span id="js-status-sentence-span-X"><span>正常</span></span>`
  のような nested 構造の場合、新 PJ の selector では外側 span の直接 text
  しか取得できず空文字になる
- 加えて空文字時の hardcoded fallback `"---"` も新 PJ には無い

**追記 (2026-05-04 後ターン): 選択肢 3 (legacy 移植) を本 issue 内で実装**。

`_parsers.py` の status 抽出を以下に置換 (legacy `mf_account.py:168-174` の
loop 形式を移植):

```python
account_status = "---"
for status_span in tds[3].css("span"):
    status_id = status_span.xpath("@id").get() or ""
    if "js-status-sentence-span-" not in status_id:
        continue
    account_status = _join_strip(status_span.css("span::text").get())
```

挙動 (legacy と byte-equivalent):
- matching span がそもそも存在しない → `"---"` fallback
- matching span 存在 + 入れ子 span text あり → その text を取得
- matching span 存在 + 入れ子 span text 空 → `""` (legacy も同じ、上書き
  によって fallback が消える)

新規 regression test:
`test_parse_accounts_status_nested_span_legacy_compat` を追加。入れ子 span
での `"正常"` 取得と、matching span 不在時の `"---"` fallback 両方を pin。

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
