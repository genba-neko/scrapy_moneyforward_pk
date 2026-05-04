# Issue #42: user 識別子表現の統合 (account_item_key + state filename)

## 前提事実 (推測でなく source あり)

実装中・plan 更新中に塗り替え禁止。記述する時はこの章を参照。

- **旧PJも multi-user 運用** (single-user ではない):
  - 出典: `scrapy_moneyforward/src/Makefile:69-161` の `_alt_*` ターゲット群
  - 環境変数 `SITE_LOGIN_USER` / `SITE_LOGIN_ALT_USER` の 2 種で
    全 spider × 全 site × 2 user の Makefile ターゲットが用意されている
  - → 旧 DynamoDB account テーブルにも 2 user 分のデータが書き込まれていた
- **旧 account `account_item_key` = `sha256(account_name)` (raw)**:
  - 出典: `scrapy_moneyforward/src/moneyforward/spiders/mf_account.py:160`
  - 主MF (`mf_account` spider) では raw が `イオンカード(本サイト)m5u*****`
    形式で suffix に user 識別子が入る → user 別に異なる sha256
  - xmf 系 (`xmf_ssnb_account` 等) では suffix 無し → **user 衝突**
- **旧 asset_allocation `asset_item_key` = `{spider.name}-{login_user}-{asset_name_en}`**:
  - 出典: `scrapy_moneyforward/src/moneyforward/spiders/mf_asset_allocation.py:117`
  - 明示的に `login_user` 連結で multi-user 完全対応
- **新 PJ session state filename = `{site}_{sha256(login_user)[:12]}.json`**:
  - 出典: `src/moneyforward_pk/auth/session_manager.py:24-42`
  - Issue #43 で導入。旧PJに source なし (旧PJ は scrapy-splash で
    state file 自体存在せず) → 新PJオリジナル独自実装
- **新 PJ account `account_item_key` = `sha256(raw_name)`**:
  - 出典: `src/moneyforward_pk/spiders/_parsers.py:201`
  - 旧 `sha256(account_name)` をそのまま継承

### 推測タグ厳守

以下の語が plan / コミット文 / PR 文に出たら、対応する file:line 引用が
必須。引用無しで書くな:

- 「実質」「おそらく」「と思われる」「だったはず」
- 「single-user」「multi-user」(必ず Makefile / config 引用付き)
- 旧PJ の運用形態に関するすべての断定

## 背景

PR #40 で multi-account クロールに対応したが、user 識別子の取り扱いが
プロジェクト内で統一されていない。具体的には:

1. **`account_item_key`** (account spider 出力 SK): 旧PJから継承した
   `sha256(raw_name)` のままで `login_user` を含まず、multi-user で衝突する。
2. **state ファイル名** (Playwright storage_state): 新PJで Issue #43 導入時に
   `{site}_{sha256(login_user)[:12]}.json` という独自 hash 形式を採用したが、
   `.work/作業メモ.txt` で「ランダムっぽい、認証ステートがわかる名前に」と
   既に指摘済み。

両者とも本来は asset_allocation の SK 形式 `{spider}-{login_user}-{識別子}`
(旧 `mf_asset_allocation.py:117` / 新 `_parsers.py:156` で実装済み) に
揃えるべきなのに、それぞれ独自 hash を採用していて整合が取れていない。

`scrapy_moneyforward_pk` は将来 DynamoDB 層と連携する前提のため、DynamoDB
schema (`PK=year_month_day`, `SK=account_item_key`) を維持しつつ
multi-user/multi-site で SK 衝突しない形に揃える必要がある。同時に、
state ファイル名も可読化して運用上の判別を容易にする。

## 識別子の棚卸し

| 識別子 | 出所 | 内容例 | 安定性 |
|---|---|---|---|
| `login_user` | env `SITE_LOGIN_USER` / `crawl_runner` 引数 | `primary@example.com` | 高 (アカウント固有) |
| `spider.name` | spider クラス属性 | 旧: `mf_account` / `xmf_ssnb_account` ...<br>新: `account` (3 spider に統合) | 高 |
| `site` | 新PJ独自、`-a site=xmf_ssnb` 引数 | `mf` / `xmf_ssnb` / `xmf_mizuho` ... | 高 |
| `raw_name` | HTML `td[0]` 抽出 | 主MF: `イオンカード(本サイト)m5u*****`<br>xmf系: `住信SBIネット銀行` | 主MF の suffix は MF UI 仕様依存 |
| `account_name` | `raw_name` から `(本サイト).*` を trim | `イオンカード` | 高 |
| `asset_name_en` | href `#portfolio_det_depo` から抽出 | `portfolio_det_depo` | 高 |

旧PJ spider 名 ↔ 新PJ `(spider_name, site)` 対応表:

| 旧 spider name | 新 spider_name | 新 site arg |
|---|---|---|
| `mf_account` | `account` | `mf` |
| `xmf_ssnb_account` | `account` | `xmf_ssnb` |
| `xmf_mizuho_account` | `account` | `xmf_mizuho` |
| (他 xmf_*_account 同様) | `account` | `xmf_*` |

## 新旧対応表 (全体)

| 項目 | 旧PJ (`scrapy_moneyforward`) | 新PJ (`scrapy_moneyforward_pk`) |
|---|---|---|
| **spider 名 (account)** | `mf_account`, `xmf_ssnb_account`, `xmf_mizuho_account`, `xmf_jabank_account`, `xmf_smtb_account`, `xmf_linkx_account`, `xmf_okashin_account`, `xmf_shiga_account`, `xmf_shiz_account` | `account` (1個に統合、`-a site=xxx` で site 切替) |
| **spider 名 (transaction)** | `mf`, `xmf_*` 多数 | `transaction` (1個) |
| **spider 名 (asset_allocation)** | `mf_asset_allocation`, `xmf_*_asset_allocation` 多数 | `asset_allocation` (1個) |
| **site 識別** | spider 名に埋込 | `-a site=xmf_ssnb` 引数で渡す |
| **login_user** | env `SITE_LOGIN_USER` / `SITE_LOGIN_ALT_USER` (Makefile `_alt_*` ターゲット) | env or `crawl_runner` 引数 (`config/accounts.yaml`) |
| **account_item_key** (SK) | `sha256(account_name)` (raw 込み)<br>(`mf_account.py:160`) | `sha256(raw_name)` (旧と同式)<br>(`_parsers.py:201`) |
| **asset_item_key** (SK) | `{spider.name}-{login_user}-{asset_name_en}`<br>(`mf_asset_allocation.py:117`) | `{spider_name}-{login_user}-{asset_type}`<br>(`_parsers.py:156`) |
| **transaction SK** | `data_table_sortable_value` | 同 |
| **transaction PK** | `year_month` | 同 |
| **account/asset PK** | `year_month_day` | 同 |
| **永続化先** | DynamoDB (3 テーブル)<br>(`dynamodb/table_*/dynamodb.yml`) | JSON 配列 3 ファイル<br>(`runtime/output/moneyforward_{type}.json`) |
| **Pipeline** | `DynamoDbPipeline` (boto3 batch_writer) | `JsonArrayOutputPipeline` |
| **認証方式** | scrapy-splash + Lua スクリプト (毎回ログイン) | Playwright + storage_state 永続化 (Issue #43) |
| **session state file** | なし (ステートレス) | `runtime/state/{site}_{sha256(login_user)[:12]}.json`<br>(`auth/session_manager.py:24-42`) |
| **dict 重複排除 (account)** | `account_items[account_item_key] = ...` リトライ中の重複排除<br>(`mf_account.py:187`) | なし (orchestrator 側でリトライ吸収) |
| **multi-account 運用** | Makefile `_alt_*` ターゲットで 2 user サポート<br>(`src/Makefile:69-161`) | PR #40 (`config/accounts.yaml` で複数 user 順次クロール) |
| **通知** | `slackweb` 直接呼出 | `SlackNotifierExtension` |
| **CloudFormation/IaC** | `dynamodb/*/dynamodb.yml` | なし |

## マルチユーザ互換 対応表

| spider | 旧PJ multi-user 対応 | 新PJ multi-user 対応 | 課題 |
|---|---|---|---|
| **transaction** | 未対応 (SK = `data_table_sortable_value` のみ、user 識別子なし) | 未対応 (継承) | 別 issue で扱う |
| **account** | 部分対応 (主MF のみ raw_name の `(本サイト)m5u*****` suffix で偶然区別、xmf 系は衝突) | 部分対応 (継承) | **issue #42** |
| **asset_allocation** | 完全対応 (`{spider}-{login_user}-{識別子}` 連結、`mf_asset_allocation.py:117`) | 完全対応 (継承、`_parsers.py:156`) | なし |
| **session state file** | 該当なし (ステートレス認証) | hash 使用 (filename 不可読、issue #42 統合スコープ) | **issue #42** で揃える |

→ asset_allocation だけが旧PJで明示的に multi-user 対応されていた。
account / transaction は旧PJ時代から未対応で、新PJもそれを継承。
issue #42 で account と state file を asset_allocation と同形式に揃える。

## キー組み立て対比 (旧 / 新)

### transaction

| | PK | SK | user/site 識別 |
|---|---|---|---|
| 旧 [`mf_transaction.py:204,253`] | `year_month` (`{:04}{:02}`) | `data_table_sortable_value` (HTML attr) | **なし** |
| 新 [`_parsers.py:76`] | 同 | 同 | **なし** |

→ 異 user の transaction が同月・同 sortable_value で衝突する余地あり。
本 issue 範囲外だが要追跡 (別 issue 化)。

### account ← 本 issue 対象 1

| | PK | SK |
|---|---|---|
| 旧 [`mf_account.py:160`] | `year_month_day` | `sha256(account_name)` (raw)<br>主MF: `(本サイト)m5u*****` 含み user 識別される<br>xmf系: suffix 無し → user 衝突 |
| 新 [`_parsers.py:201`] | 同 | `sha256(raw_name)` (旧と同式) |

両PJ共通で xmf 系では衝突する積み残し。

### asset_allocation (`{spider}-{login_user}-{識別子}` 形式)

| | PK | SK |
|---|---|---|
| 旧 [`mf_asset_allocation.py:117`] | `year_month_day` | `{spider.name}-{login_user}-{asset_name_en}` |
| 新 [`_parsers.py:156`] | 同 | `{spider_name}-{login_user}-{asset_type}`<br>(spider_name は新では合成: `{site}_{spider_type}`) |

→ 旧から **明示的に user/site 連結済み**、両PJで完全対応。
本 issue で account / state filename をこの形式に揃える。

## hash 使用箇所 悉皆調査

### 旧PJ (`scrapy_moneyforward`)

| # | 場所 | 用途 |
|---|---|---|
| 1 | `mf_account.py:160` | **生成** `sha256(account_name)` |
| 2 | `mf_account.py:181` | **Item 値設定** |
| 3 | `mf_account.py:187` | **dict キー (重複排除)** `account_items[account_item_key] = account_item` |
| 4 | pipeline `DynamoDbPipeline` 経由 | **DynamoDB SK 値として永続化・クエリ可能** |
| 5 | `dynamodb/table_moneyforward_account/dynamodb.yml:37,44` | **CloudFormation Schema** |

→ 旧 PJ では **DynamoDB SK としての本来用途** + **リトライ中のポーリング重複排除** で実際に消費されていた。

### 新PJ (`scrapy_moneyforward_pk`)

| # | 場所 | 用途 |
|---|---|---|
| 1 | `_parsers.py:201` | **生成** `sha256(raw_name)` |
| 2 | `_parsers.py:221` | **Item 値設定** |
| 3 | `pipelines.py` (`JsonArrayOutputPipeline`) | **JSON 配列フィールドとして出力**のみ |
| 4 | `tests/test_account_parse_unit.py:49` ほか | テストで生成安定性をアサート |

→ **消費なし** (DynamoDB なし、reports は account データを読まない、dict 重複排除も消失)。
hash は事実上「**将来 DynamoDB 連携した時のための予約フィールド**」状態。

### 旧→新の差分

| 観点 | 旧 PJ | 新 PJ |
|---|---|---|
| 生成 | あり | あり |
| Item 値 | あり | あり |
| dict 重複排除 | **あり** (リトライ用) | **なし** (orchestrator 側でリトライ吸収) |
| 永続化先 | DynamoDB SK | JSON 出力フィールド |
| 消費 | DynamoDB クエリ | なし |

## state ファイル名 hash の調査 ← 本 issue 対象 2

### 現状

[`src/moneyforward_pk/auth/session_manager.py:24-42`](src/moneyforward_pk/auth/session_manager.py#L24):

```python
def _hash_user(login_user: str) -> str:
    return hashlib.sha256(login_user.encode("utf-8")).hexdigest()[:12]

# ...
self.state_path = self.state_dir / f"{site}_{suffix}.json"
```

実物例: `xmf_shiga_51961713af71.json` / `xmf_ssnb_b14a8c36b4e0.json` 等。
suffix `51961713af71` / `b14a8c36b4e0` は user A / B の `sha256(email)[:12]`。

### 由来

- **新PJオリジナル** (Issue #43 で導入)。`scrapy_smbcnikko_pk` の
  `PasskeySessionManager` を参考。
- 旧PJ (`scrapy_moneyforward`) は scrapy-splash + Lua スクリプトで
  毎回ステートレスにログインしていた → **session state file 自体が存在しなかった**。
- 旧PJ から hash 採用を継承したものではない (asset_allocation の連結方式に
  揃える選択肢があったが、独自実装になった)。

### コメントによる採用理由

[`session_manager.py:24-31`](src/moneyforward_pk/auth/session_manager.py#L24):
> Used as a filename component so the state file path does not leak the
> [login_user]

= login_user を filesystem 上に直接出さないため、というセキュリティ建前。

### 妥当性検討

- state ファイルは `runtime/state/` 配下 (gitignore 対象であるべき → 要確認)
- ファイル中身に session cookie が入っており filename 以上に sensitive
- → **filename だけ hash する意味は薄い**。`.work` メモの「ランダムっぽい」
  指摘と整合する評価。

## 採用方針

### 統合方針: asset_allocation 形式に揃える

旧PJ asset_allocation で確立した「**`{spider}-{login_user}-{識別子}` 連結**」
パターンに、`account_item_key` と state ファイル名の両方を揃える。

#### 1. `account_item_key`

```python
account_item_key = "{}-{}-{}".format(spider_name, login_user, account_name)
```

- `spider_name` = `{site}_account` 合成 (asset_allocation と同じ作り方)
- `login_user` = ログインユーザー
- `account_name` = trim 後の表示名 (raw_name の `(本サイト).*` 除去後)

#### 2. state ファイル名

```python
self.state_path = self.state_dir / f"{site}_{masked_user}_{hash8}.json"
```

形式: `{site}_{local先頭3字}xxx_{domain先頭3字}xxx_{sha256(login_user)[:8]}.json`

- 先頭3字のみ可読 + 残りは固定伏字 `xxx` で長さ情報も漏らさない
- 末尾 8 字 hash で衝突防止 + 同 prefix の別 user を一意化
- `*` は Windows filename 不可 → `x` で代替

実例:

| login_user | filename |
|---|---|
| `test-user@example.com` | `xmf_shiga_tesxxx_exaxxx_51961713.json` |
| `primary@example.com` | `xmf_shiga_prixxx_exaxxx_b14a8c36.json` |
| `a@b.c` (3字未満) | `xmf_shiga_a_b_a1b2c3d4.json` (3字未満はそのまま) |

実装 (`auth/session_manager.py`):
```python
def _mask_user(login_user: str) -> str:
    """Mask login_user for filesystem use: keep first 3 chars + fixed mask + hash."""
    local, _, domain = login_user.partition("@")
    domain_head = domain.split(".", 1)[0] if domain else ""
    def _mask(s: str) -> str:
        return s if len(s) < 3 else f"{s[:3]}xxx"
    head = f"{_mask(local)}_{_mask(domain_head)}" if domain_head else _mask(local)
    digest = hashlib.sha256(login_user.encode("utf-8")).hexdigest()[:8]
    return f"{head}_{digest}"

# SessionManager.__init__:
suffix = _mask_user(login_user) if login_user else "anon"
self.state_path = self.state_dir / f"{site}_{suffix}.json"
```

理由 (情報漏洩 vs 可読性のバランス):
- 完全 email 露出は不可 (`session_manager.py:24-27` の元設計意図)
- 完全 hash は不可読 (`.work/作業メモ.txt:5` の指摘)
- 先頭3字 + hash 併用で「どのアカウントか人間が認識できる」かつ「全情報は出ない」

### 「旧互換」の意味 (account_item_key)

ここでの旧互換 = **旧 DynamoDB schema 互換** + **旧 PJ asset_allocation
の確立パターン踏襲**。
account の旧 SK 値 (`sha256(account_name)`) と完全一致させる意味ではない
(それでは multi-account 対応にならない)。新キー値は旧キー値と異なるが、
schema (PK/SK 構造) と user 識別パターンは統一される。

### 衝突懸念の検討

- **(login_user, site, account_name) は実質一意**:
  MoneyForward の account list は金融機関単位で 1 行表示。
  同一 user が同じ金融機関を二重登録することは MF 仕様上不可能。
  普通預金/定期預金等は institution 単位で集約表示されるため別行にならない。
  → 本形式で衝突発生せず。

## 実装スコープ

### A. account_item_key 連結化

#### A-1. キー組み立て修正 (`src/moneyforward_pk/spiders/_parsers.py`)

`parse_accounts()` のシグネチャ拡張:

- 現状: `parse_accounts(response, today=None)` → `spider.name` / `login_user` を受け取らない
- 変更: `parse_accounts(response, spider_name, login_user, today=None)`
  (`parse_asset_allocations` と同様のシグネチャに揃える)

`account_item_key` 生成式:

```python
account_item_key = f"{spider_name}-{login_user}-{account_id}"
```

`spider_name` の値は asset_allocation と同様 `{site}_{spider_type}` 合成形式
(例: `mf_account`, `xmf_ssnb_account`) を渡す。

#### A-2. 呼び出し側修正 (`src/moneyforward_pk/spiders/account.py`)

`parse_accounts()` 呼び出しに `spider_name` / `login_user` を渡す。
asset_allocation spider の呼び出し方を踏襲。

#### A-3. テスト更新

- `tests/test_account_parse_unit.py`: 新キー形式を反映
- `tests/test_parsers_legacy_fixtures_unit.py`: 同
- `tests/test_items_unit.py`: フィールド型は変わらないので変更不要 (要確認)
- 新規: multi-user (同一金融機関を 2 user で登録) のケース

### B. state ファイル名可読化

#### B-1. `_hash_user` を `_mask_user` に置換 (`src/moneyforward_pk/auth/session_manager.py`)

```python
def _mask_user(login_user: str) -> str:
    local, _, domain = login_user.partition("@")
    domain_head = domain.split(".", 1)[0] if domain else ""
    def _mask(s: str) -> str:
        return s if len(s) < 3 else f"{s[:3]}xxx"
    head = f"{_mask(local)}_{_mask(domain_head)}" if domain_head else _mask(local)
    digest = hashlib.sha256(login_user.encode("utf-8")).hexdigest()[:8]
    return f"{head}_{digest}"
```

#### B-2. state ファイル名を `{site}_{masked_user}.json` 形式に変更

#### B-3. 旧 hash 形式 state ファイルの取扱い

- 既存 `{site}_{hex12}.json` は別物として共存
- 起動時に新形式が無く旧形式があれば再ログイン (= 通常のログインフロー)
- 移行ヘルパは作らず、運用で旧ファイルを手動削除

#### B-4. テスト更新

- `tests/test_session_manager_unit.py` (該当するもの) のファイル名検証
- 新規: `_safe_user` の sanitize ケース (記号エスケープ)

### C. ドキュメント更新

- `CONTRIBUTING.md:86`: `account` の SK 説明を更新
- `plan/rules/RULES3_PROGRAMMING.md:121`: 同
- `src/moneyforward_pk/items.py:48` のコメント (`# range key (sha256 of name)`) を更新
- `src/moneyforward_pk/auth/session_manager.py` の docstring 更新
  (「does not leak the login_user」記述の見直し)

### D. fixture (任意)

`tests/fixtures/mf_accounts_legacy.html` 1 件のみ。
multi-user 検証のため別 fixture (xmf 系で user 違いの 2 件想定) があると
理想だが、無くても unit test で `parse_accounts` を 2 回 (login_user 違い)
呼び出して検証可能。

## 未決事項

### 旧 DynamoDB データの取扱い (DynamoDB 層連携時)

新キー形式に切り替えると、旧 DynamoDB に蓄積された
`sha256(account_name)` 形式のレコードと新キーは別物として共存する。
連携開始時に以下のいずれかを選ぶ:

- (a) 旧データを rewrite ジョブで新キー形式に変換
- (b) 旧データはそのまま残し、新キー形式で書き続ける (クエリ層で吸収)
- (c) 旧データを破棄し新キーで再構築

DynamoDB 連携実装時に別 issue で扱う。本 issue では Scrapy 出力 (JSON) の
キー形式変更までを範囲とする。

### `runtime/state/` の gitignore 状態

state ファイル名可読化前に `.gitignore` で `runtime/state/` が除外されている
ことを実装時に確認する。除外されていなければ可読化前に gitignore 追加が
必要 (login_user 漏洩防止)。

### transaction の user 識別 (issue 範囲外)

transaction の SK (`data_table_sortable_value`) も user 識別子を含まない
ため、multi-user で衝突する可能性がある。本 issue とは別 issue で扱う。

## 完了判定

- [x] 方針確定 (asset_allocation 形式に統合) ← 本 plan で確定
- [ ] A-1: `parse_accounts` シグネチャ拡張 + 新キー形式実装
- [ ] A-2: `account.py` (spider) の呼び出し更新
- [ ] A-3: account 関連テスト更新 + multi-user ケース新規追加
- [ ] B-1: `_hash_user` を `_safe_user` に置換
- [ ] B-2: state ファイル名形式変更
- [ ] B-3: 旧形式 state ファイル取扱い方針の文書化
- [ ] B-4: session_manager テスト更新
- [ ] C: ドキュメント (CONTRIBUTING / RULES3 / コメント / docstring) 更新
- [ ] `runtime/state/` の gitignore 確認
- [ ] `pytest tests/ -v` パス
- [ ] `ruff check src/ tests/` クリーン
- [ ] `pyright src/ tests/` クリーン
- [ ] PR 作成・本 plan ファイルを issue #42 「関連資料」にリンク

## ブランチ

`feature/42_account_item_key_login_user` (作成済み)

state filename も含むので将来的にブランチ名変更も検討
(例: `feature/42_user_id_unification`)。ただし PR 作成前なので現状維持で進める。

## 関連

- Issue #42 (本件)
- Issue #40 / PR #40 (multi-account orchestrator 導入で本問題顕在化)
- Issue #41 (reports 出力フォーマット — downstream で新キー利用する場合関連)
- Issue #43 (Playwright session 永続化 — state filename hash 導入元)
- `.work/作業メモ.txt` (state ファイル名可読性の元指摘)
