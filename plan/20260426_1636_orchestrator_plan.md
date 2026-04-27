# Multi-account Crawl Runner 実装プラン (v3)

作成: 2026-04-26 16:36
更新: 2026-04-26 (Opus レビュー反映)
Issue: #40
ブランチ: `feat/40_variant_orchestrator`

## 目的

11 サイト × 複数アカウント × 3 spider 種別を順次クロールする `crawl_runner` を実装する。同時に site ごとに分岐していた spider クラス群を統合する。

## 確定事項

| 項目 | 内容 |
|---|---|
| 実行方式 | Python CLI (`crawl_runner.py`) + `CrawlerRunner` + `defer.inlineCallbacks` で sequential 実行 |
| 起動単位 | spider 1 起動 = 1 (site, account, spider 種別) の組 |
| アカウント設定 | YAML config (`config/accounts.yaml`、`.gitignore` 対象) ※ 要再考の含み残 |
| Site 定義 | `registry.py` 維持。 11 サイト (mf + xmf + xmf_ssnb / xmf_mizuho / xmf_jabank / xmf_smtb / xmf_linkx / xmf_okashin / xmf_shiga / xmf_shiz) |
| Spider クラス | 3 個に集約 (`transaction` / `account` / `asset_allocation`)。site は spider 引数で渡す。**派生クラス 27 ファイル削除** |
| spider.name | クラス固定 ("transaction" 等)、override しない |
| login_flow | `MoneyforwardBase.login_flow` を `is_partner_portal` で 2 分岐統合。**`XMoneyforwardLoginMixin` 削除** |
| 出力 key (asset_allocation のみ) | parser で `f"{spider.variant.name}_{spider.spider_type}-{user}-{type}"` 組立 (元 PJ 互換) |
| 出力 key (account) | 既存通り `hashlib.sha256(account_name)` (spider 名非依存) |
| 出力 key (transaction) | key フィールドなし (元 PJ も無し) |
| 出力ファイル | 元 PJ と同じ 3 ファイル集約 (`moneyforward_transaction.json` / `_account.json` / `_asset_allocation.json`) |
| 出力形式 | **正しい JSON 配列 1 つ** (`[item1, item2, ...]`)。元 PJ の `][` 連結 invalid JSON は直す |
| pipeline 実行前 | 3 ファイルを truncate してから書込開始 (元 PJ Makefile の `clean-transaction` 相当) |
| PR #18 alt-as-retry | バグ。本 Issue で削除。`login_retry_times` は session retry の上限ガードとしてのみ機能、上限超過で spider 終了 + stats マーク |
| Playwright cleanup | accepted risk として現状維持。問題発生時に別 Issue で subprocess 分離検討 |
| 並列実行 | 非対応 (sequential のみ) |
| 終了コード | 0=全成功、1=1件以上失敗 |

## YAML config 形式

```yaml
# config/accounts.yaml
mf:
  - user: a@x.com
    pass: pwd1
  - user: b@x.com
    pass: pwd2
xmf_ssnb:
  - user: c@y.com
    pass: pwd3
xmf_jabank:
  - user: d@z.com
    pass: pwd4
# (xmf_mizuho など未設定 → orchestrator iteration 対象外)
```

site のキーは `VARIANTS` のキーと一致。最低限のキー存在チェックのみ (詳細 schema 検証は将来 Issue)。

## 実装

### ファイル構成

```
src/moneyforward_pk/
├── crawl_runner.py              # 新規: CLI エントリ
├── _runner_core.py              # 新規: load_accounts / list_invocations / run_all / summarize
├── spiders/
│   ├── transaction.py           # site 引数受付に拡張
│   ├── account.py               # 同上
│   ├── asset_allocation.py      # 同上
│   ├── base/moneyforward_base.py  # site/login_user/login_pass kwargs 受付、login_flow 2分岐統合、alt-as-retry 削除
│   └── (xmf_*.py 27 ファイル削除)

config/
├── accounts.yaml                # 新規 (.gitignore)
└── accounts.example.yaml        # テンプレ
```

### CLI

```bash
cd src && python -m moneyforward_pk.crawl_runner                # 全 site × 全 account × 全種別
cd src && python -m moneyforward_pk.crawl_runner --type transaction
cd src && python -m moneyforward_pk.crawl_runner --site xmf_ssnb
cd src && python -m moneyforward_pk.crawl_runner --list         # 起動予定一覧 (実行しない)
```

### Spider 改修

```python
class MoneyforwardBase(scrapy.Spider):
    spider_type: str  # サブクラスで定義 ("transaction" / "account" / "asset_allocation")

    def __init__(self, *args, site=None, login_user=None, login_pass=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._site_override = site
        self._login_user_override = login_user
        self._login_pass_override = login_pass

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        site = spider._site_override or "mf"
        spider.variant = VARIANTS[site]
        spider.login_user = spider._login_user_override or crawler.settings.get("SITE_LOGIN_USER", "")
        spider.login_pass = spider._login_pass_override or crawler.settings.get("SITE_LOGIN_PASS", "")
        return spider

    def login_flow(self, ...):
        if self.variant.is_partner_portal:
            # XMoneyforwardLoginMixin の旧ロジック (sign_in_session_service)
            ...
        else:
            # 既存 mfid_user 系ロジック
            ...
```

`XMoneyforwardLoginMixin` クラスは削除。

### Parser の key 組立 (asset_allocation のみ)

```python
# _parsers.py の parse_assets
asset_item_key = f"{spider.variant.name}_{spider.spider_type}-{login_user}-{asset_type}"
```

`parse_transactions` は変更なし (key フィールドなし)。`parse_accounts` も変更なし (`hashlib.sha256` ベース)。

### 起動シーケンス

```python
@defer.inlineCallbacks
def run_all(invocations, settings, results):
    runner = CrawlerRunner(settings)
    for inv in invocations:  # (spider_type, site, user, pass)
        try:
            yield runner.crawl(inv.spider_type, site=inv.site, login_user=inv.user, login_pass=inv.pwd)
            results[inv] = "succeeded"
        except Exception as e:
            results[inv] = f"failed: {e.__class__.__name__}"
```

### Pipeline 改修

- 出力ファイル名: 3 ファイル固定 (`moneyforward_{spider_type}.json`)
- 各 invocation 開始**前**に truncate (orchestrator が起動前に 3 ファイルを `[]` で初期化、または `clean-` 相当の delete-then-write)
- 各 spider は **正しい JSON 配列に append** (`[`...`]` 1 つだけ)。実装は既存 `JsonOutputPipeline` を JSONL → JSON 配列 mode に変更
- 複数 spider が同一ファイルに書く際の整合: orchestrator が「ファイルを開いて配列を書き続ける」モード (open_spider で `[` を書かず、close_spider で `]` を書かず、orchestrator 全体終了時に最終 `]` を付ける) 等の機構が必要

具体実装は T5 で詰める。

### 終了コード

| code | 意味 |
|---|---|
| 0 | 全 spider 成功 |
| 1 | 1 件以上失敗 |

エラーハンドリング詳細・アラート通知は別レイヤー (cron 上のラッパースクリプト等) で実装。

## タスク

| # | 内容 | 工数 |
|---|---|---|
| T1 | `_runner_core.py`: `load_accounts()` (YAML パース、最低限のキーチェック) + `list_invocations()` | S |
| T2a | `MoneyforwardBase` 改修: site/login_user/login_pass kwargs 受付 | S |
| T2b | `login_flow` を `is_partner_portal` 分岐で 2 系統統合、`XMoneyforwardLoginMixin` 削除 | M |
| T2c | alt-as-retry 削除: `_resolve_credentials` / `login_attempt` 引数削除、middleware の `login_retry_times` を session retry 上限ガードに整理 | S |
| T3 | xmf_* 27 ファイル削除 + 既存テストの site 引数化対応 | S |
| T4 | parser の `asset_item_key` 組立を `spider.variant.name` 経由に変更 | S |
| T5 | pipeline.py: 出力ファイル名を 3 ファイル集約、正しい JSON 配列形式、orchestrator 開始時 truncate 機構 | M |
| T6 | `_runner_core.py`: `run_all` defer + `summarize()` + `_exit_code()` | S |
| T7 | `crawl_runner.py`: argparse + `main()` + reactor install | S |
| T8 | tests: `test_crawl_runner_unit.py` (load_accounts / list_invocations / summarize / run_all defer mock) | S |
| T9 | `job_runner.sh` 引数 (transaction/asset/account) 互換維持して内部 crawl_runner 呼出 | S |
| T10 | `.gitignore` (`config/accounts.yaml`) + `accounts.example.yaml` 整備 | S |
| T11 | `.env.example` 更新 (`SITE_LOGIN_*` 削除)、`settings.py` の env 読込整理、README、CLAUDE.md (Spider 起動範囲) 更新 | S |

合計 9S + 2M = ~16h (現実 24-32h)。

## 完了判定

- [ ] T1〜T11 実装完了
- [ ] pytest 全 pass
- [ ] ruff clean
- [ ] `--list` で全起動予定が列挙される
- [ ] `job_runner.sh transaction` の引数互換動作確認
- [ ] 出力ファイル (`moneyforward_*.json` 3 ファイル) が **正しい JSON 配列としてパース可能** (`json.load()` 成功)
- [ ] xmf_* 27 ファイル削除確認
- [ ] PR 作成 → master マージ
- [ ] Issue #40 クローズ

## Out of scope (将来 Issue)

- YAML schema 厳密検証 (pydantic / jsonschema)
- `--account` 引数による単一アカウント再実行
- E2E テスト (出力 byte-diff)
- Playwright cleanup の subprocess 分離 (発生時対応)
- Slack 通知の集約 (現状 30 spider 分の spam 状態)
- log file の spider 別分離
