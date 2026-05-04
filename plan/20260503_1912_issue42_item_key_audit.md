# Issue #42: 旧/新 PJ における item_key 構成要素 悉皆調査

ユーザー指示に基づく事実調査。推測なし。すべて file:line + 具体値で記述。

---

## ① 旧 PJ (`scrapy_moneyforward`) の SK 構成要素 (file:line + 値)

### transaction (`mf_transaction.py`)

| 項目 | 出典 | 抽出元 (HTML) | 値の例 |
|---|---|---|---|
| SK 値 | `mf_transaction.py:204` | `td.date::attr(data-table-sortable-value)` | `2020/06/01-006908130171` |
| SK 名 | `mf_transaction.py:204` | `data_table_sortable_value` | (同上) |
| PK | `mf_transaction.py:253` | `{:0=4}{:0=2}".format(year, month)` (sortable_value から抽出) | `202006` |

SK は HTML 属性 `data-table-sortable-value` の生値。`{date}-{seq}` 形式の MF 内部 ID。

### asset_allocation (`mf_asset_allocation.py`)

| 項目 | 出典 | 抽出元 (HTML) | 値の例 |
|---|---|---|---|
| SK 値 | `mf_asset_allocation.py:117` | `"{}-{}-{}".format(self.name, self.login_user, asset_name_en)` | `mf_asset_allocation-finance@dds-net.org-portfolio_det_depo` |
| SK 第3要素 (`asset_name_en`) | `mf_asset_allocation.py:106` | `th a::attr(href)` の `#` 以降 (例: `/bs/portfolio#portfolio_det_depo`) | `portfolio_det_depo` |
| SK 第1要素 (`self.name`) | spider クラス属性 | クラスごとに固定 | `mf_asset_allocation` / `xmf_ssnb_asset_allocation` 等 |
| SK 第2要素 (`self.login_user`) | `mf_transaction.py:47` | `os.environ['SITE_LOGIN_USER']` | `finance@dds-net.org` |
| PK | `mf_asset_allocation.py:118` | `today` から `{:0=4}{:0=2}{:0=2}` 整形 | `20230522` |

### account (`mf_account.py`)

| 項目 | 出典 | 抽出元 (HTML) | 値の例 |
|---|---|---|---|
| SK 値 | `mf_account.py:160` | `hashlib.sha256(account_name.encode()).hexdigest()` | `0046023369873246db3f67380d4692fb4dd0ad2eefb1a47f423f6c943e679798` |
| SK 元データ (`account_name`, sha256 入力) | `mf_account.py:159` | `td[0].css("*::text").getall()` を join (raw、`(本サイト)m5u*****` suffix 込み) | `イオンカード(本サイト)m5u*****` |
| 表示用 `account_name` | `mf_account.py:162-164` | 上記 raw から `(本サイト).*` を trim | `イオンカード` |
| PK | `mf_account.py:180` | `datetime.now().strftime('%Y%m%d')` | `20230522` |

---

## ② 各 spider の選択は forced か arbitrary か

各 spider の HTML から取得可能な代替識別子と、実際の選択を比較。

### transaction

| 取得可能な per-row 識別子 | 実選択? | 採否理由 |
|---|---|---|
| `td.date::attr(data-table-sortable-value)` (= `2020/06/01-006908130171`) | ✓ 採用 | per-row 一意の MF 内部 ID。実質 forced (これ以外に per-row 一意 identifier なし) |
| `td.content` テキスト, amount, lctg, mctg 等 | ✗ | 一意性保証なし。同日同金額同 content の重複可能 |

→ **forced** (他に per-row 一意 identifier が HTML 上に見つからない)。

### asset_allocation

| 取得可能な per-category 識別子 | 実選択? | 採否理由 |
|---|---|---|
| `th a::attr(href)` の `#portfolio_det_depo` 部 | ✓ 採用 (`asset_name_en`) | URL fragment、ASCII slug、安定 |
| `th a::text` (日本語: `預金・現金・暗号資産`) | ✗ | 日本語、表示用 (Item の `asset_name` field に分離保存) |

→ **forced 寄り** (URL fragment が ASCII canonical で per-category 一意、これ以外の妥当な選択肢なし)。日本語 vs ASCII の選択は意図的。

### account

| 取得可能な per-row (per-institution) 識別子 | 実選択? | 採否理由 |
|---|---|---|
| `<tr id="ugZaexXKVFaIM8GMCrVlCQ">` (Base64URL canonical) | ✗ | **使われていない** (旧 PJ も新 PJ も) |
| `<a href="/accounts/show/{ID}">` (同じ Base64URL canonical) | ✗ | **使われていない** |
| `<input name="account_id_hash" value="{ID}">` (同じ Base64URL canonical) | ✗ | **使われていない**。但し旧 PJ `analysis/account_analysis.md:54` には HTML サンプル記載あり (= 旧 PJ 作者は存在を把握していた) |
| raw text (`イオンカード(本サイト)m5u*****`) を sha256 | ✓ 採用 | 旧 PJ の選択。`m5u*****` suffix を含むので主MF サイトでは結果的に user 別に異なる hash が出る |

→ **arbitrary** (ASCII canonical Base64URL が同じ HTML 内に 3 箇所も存在するのに、Japanese 表示名を sha256 する選択を旧 PJ 作者がした)。理由は legacy author しか分からないが、客観的には HTML 上に明らかにより適切な per-row canonical identifier がある。

---

## ③ 旧 PJ vs 新 PJ (`moneyforward_pk`) 状況対比

| spider | 観点 | 旧 PJ | 新 PJ | 一致? |
|---|---|---|---|---|
| **transaction** | SK 抽出元 | `td.date::attr(data-table-sortable-value)` (`mf_transaction.py:204`) | `row.css("td.date::attr(data-table-sortable-value)")` (`_parsers.py:49`) | ✓ |
| | SK 値の例 | `2020/06/01-006908130171` | (同) | ✓ |
| | PK | `year_month` 整形 | (同) `_parsers.py:39,74` | ✓ |
| | login_user 連結 | なし | なし | ✓ |
| | multi-user 衝突 | あり (同月・同 sortable_value で別 user record が衝突) | あり (継承) | ✓ (積み残し継承) |
| **asset_allocation** | SK 抽出元 | `th a::attr(href)` の `#` 以降 (`mf_asset_allocation.py:106`) | `row.css("th a::attr(href)").get` の `#` 以降 (`_parsers.py:151-152`) | ✓ |
| | SK 値の例 | `mf_asset_allocation-finance@dds-net.org-portfolio_det_depo` | 同形式 (`xmf_ssnb_account-...-portfolio_det_depo`) (`_parsers.py:156`) | ✓ |
| | login_user 連結 | あり (`mf_asset_allocation.py:117`) | あり (`_parsers.py:156`) | ✓ |
| | spider_name 第1要素 | `self.name` (旧 spider クラス名) | `f"{site}_{spider_type}"` 合成 (新 PJ では account.py 等で構築) | 値の形式は同等 |
| | multi-user 衝突 | 解決済 | 解決済 (継承) | ✓ |
| **account** | SK 抽出元 | `td[0].css("*::text").getall()` (raw text) → sha256 (`mf_account.py:159-160`) | `tds[0].css("::text").getall()` (raw text) → sha256 (`_parsers.py:198,201`) | ✓ |
| | SK 値の例 | `0046023369873246db3f67380d4692fb4dd0ad2eefb1a47f423f6c943e679798` (旧 DynamoDB CSV `.work/results account.csv:2`) | 同形式 (新 PJ JSON 出力でも 64-char hex) | ✓ |
| | login_user 連結 | なし | なし | ✓ |
| | MF canonical Base64URL ID 利用 | 不使用 | 不使用 | ✓ (両者とも未利用) |
| | multi-user 衝突 | 主MFサイトでは raw_name の `(本サイト)m5u*****` suffix で偶然区別、xmf 系 (suffix なし) では衝突 | 同じ問題を継承 | ✓ (積み残し継承) |

---

## ④ 各 spider に対して「どうすべきか」テーブル

| spider | 現状の問題 | あるべき設計 | 修正範囲 | 優先度 |
|---|---|---|---|---|
| **account** (Issue #42 対象) | SK = `sha256(raw_name)` で xmf 系 multi-user 衝突。HTML 内に MF canonical Base64URL ID (`<tr id>` 等) があるのに不使用 | (案 A1) 旧 PJ asset_allocation 形式を踏襲し SK = `{spider}-{login_user}-{MF_canonical_id}` (per-row Base64URL を 3 番目に置く)<br>(案 A2) 旧 sha256 形式を保持しつつ入力に login_user を mix `sha256(login_user-raw_name)` (legacy SK shape 維持) | A1: `_parsers.py:parse_accounts` シグネチャ拡張 + Item に新フィールド追加 + tests<br>A2: `_parsers.py:201` の sha256 入力を変更のみ + tests<br>(どちらを採るかは別途決定) | **本 issue 対象** |
| **transaction** | SK = `data_table_sortable_value` のみで login_user なし。同月・同 sortable_value で異 user record が衝突可能 | (案 B1) PK or SK に login_user を含める (例: SK = `{login_user}-{sortable_value}`)<br>(案 B2) 現状維持 (single-user 運用前提) | B1: `_parsers.py:parse_transactions` シグネチャ拡張 + tests + 旧 DynamoDB データとの非互換 | **別 issue 化** (#42 範囲外) |
| **asset_allocation** | なし (旧/新とも `{spider}-{login_user}-{asset_type}` で完全対応済) | 現状維持 | なし | なし |

---

## 補足: `<tr id>` 等の Base64URL canonical ID について

- 値の例 (旧 fixture `tests/fixtures/mf_accounts_legacy.html`):
  - `ugZaexXKVFaIM8GMCrVlCQ` (イオンカード)
  - `IecN2MigxgYAiJmeWsr8xg` (エポスカード)
  - `0wfJgdZWXAD-D40iaBJ3ew` (`-` を値内に含むケース)
- 形式: 22 文字 Base64URL (推定 16 byte = 128 bit)
- 同一 HTML 内で 3 箇所に同値で出現:
  - `<tr id="...">` (table 行 id)
  - `<a href="https://moneyforward.com/accounts/show/...">` (URL path)
  - `<input type="hidden" name="account_id_hash" value="...">` (form hidden field)
- 旧 PJ の `analysis/account_analysis.md:54` に HTML 抜粋として記録 = 旧 PJ 作者は存在を把握していたが key として採用しなかった

---

## 補足: 旧 DynamoDB 実データ (CSV) の確認

| ファイル | spider | レコード例 (key 抜粋) |
|---|---|---|
| `.work/results trans.csv:2` | transaction | `data_table_sortable_value = "2020/06/01-006908130171"` |
| `.work/results aset.csv:2` | asset_allocation | `asset_item_key = "mf_asset_allocation-finance@dds-net.org-portfolio_det_depo"` |
| `.work/results account.csv:2` | account | `account_item_key = "0046023369873246db3f67380d4692fb4dd0ad2eefb1a47f423f6c943e679798"` |

旧 DynamoDB が実際に保存していたデータは上記の通り。

---

## 関連

- Issue #42 (本件)
- `plan/20260503_1457_issue42_account_item_key_login_user.md` (本件の旧 plan、本調査と対照)
- `plan/20260503_1901_issue42_reflection_recurrence_prevention.md` (本件で発生した私の失敗の反省)
- ブランチ `feature/42_account_item_key_login_user` (現状: account-related 実装は master に巻き戻し済み、session_manager の masking 実装のみ残)
