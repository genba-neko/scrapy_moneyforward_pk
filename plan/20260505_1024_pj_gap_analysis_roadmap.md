# PJ差異分析・ロードマップ (旧 scrapy_moneyforward → 本PJ)

調査日: 2026-05-05

## 背景

旧 `scrapy_moneyforward` との差異を全方位で比較・スコアリングした結果を踏まえ、
残存課題と今後の方針を整理する。

---

## 前提: 機能差異比較・スコアリング

### スパイダー設計

- **旧:** 10種類 × 3機能 = 30個の独立クラス（`mf_transaction`, `xmf_ssnb`, `xmf_mizuho` ...）
- **新:** 3クラス（`transaction`, `account`, `asset_allocation`）+ `--site` 引数で11サイト対応

### ブラウザ自動化

- **旧:** Splash（外部Docker）+ Lua スクリプト
- **新:** Playwright（Python）+ セッション永続化（`session_manager.py`）

### 出力・データ永続化

- **旧:** DynamoDB（バッチ書き込み、遅延制御付き）
- **新:** JSON ローカルファイル（`JsonArrayOutputPipeline`）

### 新PJ専用機能（旧PJに無い）

- セッション再利用 → ログイン頻度低減・bot検出回避
- `crawl_runner.py` → マルチサイト・マルチアカウント一括実行
- `PlaywrightSessionMiddleware` → セッション失効時自動リトライ
- `SlackNotifierExtension` → クロール完了通知
- `secrets/resolver.py` + Bitwarden統合 → 秘密管理
- `reports/` サブコマンド群 → レポート生成CLI統一
- `seccsv/` → 証券CSV変換
- 30+ユニットテスト

### 旧PJのみ（廃止済）

- Lua スクリプト群（Playwright移行で不要）
- DynamoDB テーブル定義（JSON移行で不要）
- スタンドアロン report スクリプト群（CLI統一で不要）

### スコア比較（各項目 /10）

| 項目 | 旧 scrapy_moneyforward | 新 scrapy_moneyforward_pk |
|------|----------------------|--------------------------|
| コード保守性 | 3 — 30スパイダー＝大量重複 | 9 — 3クラス＋Variant |
| 拡張性 | 2 — サイト追加＝スパイダー3個追加 | 9 — YAML/レジストリ1行追加 |
| セキュリティ | 4 — 認証情報がコード or 環境変数直書き | 9 — Bitwarden統合、マスク保存 |
| 安定性 | 5 — 毎回ログイン、リトライなし | 8 — セッション再利用、自動リトライ |
| テスト | 1 — テストなし | 8 — 30+ユニットテスト |
| 依存関係 | 4 — Splash Docker必須 | 7 — Playwright（ローカル完結） |
| 実行簡便性 | 5 — `scrapy crawl <name>` 個別実行 | 9 — `crawl_runner --site all` |
| 可観測性 | 4 — インラインSlack通知 | 8 — Extension分離、HTML inspector |
| データ出力柔軟性 | 6 — DynamoDB（クラウド連携◎） | 7 — JSON（シンプル、クラウド連携は別途） |
| ドキュメント | 4 — 最低限 | 7 — docstring・plan充実 |
| **合計** | **38 / 100** | **81 / 100** |

旧はDynamoDB出力のクラウド連携面のみ優位。他全項目で新が大幅上回る。

---

## 1. 移植状況サマリ

### 移植済み（完了）

| 旧PJ | 新PJ | 完了時期 |
|------|------|----------|
| `mf_transaction` 等30スパイダー | `transaction` + Variant レジストリ | PR#66以前 |
| Splash + Lua | Playwright + Python | 初期移植 |
| DynamoDB 書き込み | `JsonArrayOutputPipeline` (JSON) | 初期移植 |
| `get_balances_report.py` | `reports balances` サブコマンド | 初期移植 |
| `get_asset_allocation_report.py` | `reports asset_allocation` サブコマンド | 初期移植 |
| `get_balances_csv.py` | `reports balances_csv` サブコマンド | 初期移植 |
| `adjust_segregated_asset` / `period_dict` | `reports/segregated_asset.py` + YAML | PR#66 2026-05-05 |

### 未移植（機能ギャップ）

| 旧PJ | 内容 | 対応方針 |
|------|------|----------|
| `get_balances_blog.py` | ブログ向け収支Markdown（Google Charts埋め込み） | [完了 PR#TBD 2026-05-05] Issue #68 |
| `get_asset_allocation_blog.py` | ブログ向け資産配分Markdown（Google Charts埋め込み） | [完了 PR#TBD 2026-05-05] Issue #68 |
| DynamoDB 出力 | クラウド永続化・マルチマシン共有 | Issue #DynamoDB併用 で対応 |

---

## 2. Issue 設計

### Issue α: DynamoDB パイプライン追加（JSON併用）

**方針:** JSON廃止しない。DynamoDBパイプラインを追加し、設定で両立。

**設計:**

```
src/moneyforward/pipelines/
  json_array.py       # 既存（変更なし）
  dynamodb.py         # 新規: DynamoDbPipeline
```

`DynamoDbPipeline` 実装方針:
- `from_crawler` で `DYNAMODB_TABLE_NAME`, `DYNAMODB_PUT_DELAY`, `DYNAMODB_BATCH_N` 読込
- バッチ書き込み（旧PJ `pipelines.py` のロジックを純粋に移植）
- 有効化: `settings.py` の `ITEM_PIPELINES` に追記、`DYNAMODB_TABLE_NAME` 未設定時はno-op

```python
# settings.py 追記イメージ
ITEM_PIPELINES = {
    "moneyforward.pipelines.json_array.JsonArrayOutputPipeline": 300,
    "moneyforward.pipelines.dynamodb.DynamoDbPipeline": 400,  # TABLE_NAME未設定時no-op
}
DYNAMODB_PUT_DELAY = 3
DYNAMODB_BATCH_N = 10
```

`DYNAMODB_TABLE_NAME` 未設定 → パイプラインが `open_spider` 時に自身を無効化（例外なし）。

**ファイル:**
- 新規: `src/moneyforward/pipelines/dynamodb.py`
- 修正: `src/moneyforward/settings.py`（ITEM_PIPELINES, DYNAMODB_* 設定追加）
- 新規: `tests/test_dynamodb_pipeline_unit.py`

**受け入れ基準:**
- `DYNAMODB_TABLE_NAME` 未設定時は JSON のみ書き込み（既存動作維持）
- `DYNAMODB_TABLE_NAME` 設定時は JSON + DynamoDB 両方に書き込み
- `pytest` 全パス

---

### Issue β: ブログ出力移植（`get_balances_blog` + `get_asset_allocation_blog` + 口座分類YAML）

**方針:** A/B/C を1issueに統合。依存関係が密なため分割より一括実装が効率的。

#### 調査結果（プラン時点で確認済み）

**新PJ `reports/balances.py` に存在しない関数（新規実装必要）:**

| 旧PJ メソッド | 用途 | 新PJ での実装方針 |
|-------------|------|-----------------|
| `report_payment_for_google_chart(display_items, year, month, display_lctg)` | 支出Google Charts Markdown生成 | `reports/blog_balances.py` に純関数で新規実装 |
| `report_receipt_for_google_chart(display_items, year, month)` | 収入Google Charts Markdown生成 | 同上 |
| `get_payment_summary(year, month)` | 支出合計取得 | `aggregate_balances` の `segment` から導出（既存関数で代替可） |
| `get_receipt_summary(year, month)` | 収入合計取得 | 同上 |

新PJの `aggregate_balances` 戻り値 `{"lctg": {}, "mctg": {}, "segment": {}}` から
同等データを取り出せるため、DynamoDBクラスへの依存なしに純関数として移植可能。

**口座種別分類（200行超ハードコード → YAML外部化）:**

旧PJ `get_balances_blog.py` に以下のリストがハードコード:
- `account_type_wallet` (現金)
- `account_type_prepaid` (電子マネー)
- `account_type_mall` (主要ショッピングサイト)
- `account_type_creditcard` (クレジットカード)
- `account_type_bank` (銀行振込)

→ `config/account_types.yaml` に外部化（`segregated_asset.yaml` の先例踏襲）

**`get_asset_allocation_blog.py` :**
- `report_asset_allocation_for_google_chart` → 旧PJの `tables/asset_allocation.py` 内
  → 新PJ `reports/asset_allocation.py` に存在するか確認が必要（実装時に調査）
- 円グラフ（当月）+ 縦棒グラフ（年初比・前月比）の2種類

#### ファイル構成

新規:
```
src/moneyforward/reports/
  blog_balances.py         # ブログ向け収支Markdown生成（Google Charts）
  blog_asset_allocation.py # ブログ向け資産配分Markdown生成（Google Charts）

config/
  account_types.yaml              # 口座種別分類（.gitignore 入り）
  account_types.example.yaml      # テンプレート（コミット対象）

tests/
  test_blog_balances_unit.py
  test_blog_asset_allocation_unit.py
```

修正:
- `src/moneyforward/reports/cli.py` — `blog_balances` / `blog_asset_allocation` サブコマンド追加
- `.gitignore` — `config/account_types.yaml` 追記

#### CLIサブコマンド

```bash
python -m moneyforward.reports blog_balances -y 2026 -m 4
python -m moneyforward.reports blog_balances -y 2026 -m 4 --cost  # 生活費収支分析
python -m moneyforward.reports blog_asset_allocation -y 2026 -m 4 -d 30
```

#### 受け入れ基準

- `report_payment_for_google_chart` / `report_receipt_for_google_chart` が純関数として実装
- `account_types.yaml` 不在時は警告のみ（既存 `segregated_asset.yaml` と同パターン）
- `blog_balances -y 2026 -m 4` で Google Charts Markdown が stdout に出力
- `blog_asset_allocation -y 2026 -m 4 -d 30` で円グラフ + 縦棒グラフ Markdown 出力
- `pytest` 全パス

---

## 3. データ永続化戦略（確定）

**方針: JSON継続 + DynamoDB 追加（併用）**

```
クロール → JsonArrayOutputPipeline → runtime/output/*.jsonl  (既存・維持)
         → DynamoDbPipeline        → DynamoDB テーブル       (新規追加)
                                       ↑ DYNAMODB_TABLE_NAME 設定時のみ有効
```

- `DYNAMODB_TABLE_NAME` 未設定 → DynamoDB パイプラインは自動 no-op
- JSON は常に出力（ローカル動作・デバッグ用）
- DynamoDB は本番クラウド連携用

旧PJのスコア「データ出力柔軟性 6→7」→ 本対応後 **9** に改善見込み。

---

## 4. Issue候補まとめ

| Issue | 内容 | ラベル | 優先度 |
|-------|------|--------|--------|
| α | DynamoDB パイプライン追加（JSON併用） | `feat` | P1 |
| β | ブログ出力移植（収支+資産配分+口座分類YAML） | `feat` | P1 |

---

## ステータス

- [x] Issue α 作成 (#67 DynamoDB パイプライン追加)
- [x] Issue β 作成 (#68 ブログ出力移植)
