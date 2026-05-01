# PR #40 E2E 検証で判明した残不具合 (3件)

作成: 2026-04-29 21:58
ブランチ: (新規ブランチ未切り出し / 起点 `feat/40_variant_orchestrator`)
関連 PR: #47 (feat/40_variant_orchestrator)

## 背景

PR #47 (Issue #40 の orchestrator 実装) を rebase して E2E 動作させた結果、
以下 3 件の不具合を確認。 PR #40 を merge する前に対応必要。

E2E 実行ログ: `runtime/logs/moneyforward_pk.log` 14:34〜21:47。
出力ファイル: `runtime/output/moneyforward_{transaction,account,asset_allocation}.json`。

実行サマリ抜粋:

```
=== Crawl Runner Summary ===
Total invocations:  1
Succeeded:          1
Failed:             0
Elapsed:            25893.8s   (うち約 7 時間ハング)
```

実態 (ログから再構築):

| # | invocation | 開始 | 結果 | items |
|---|------------|------|------|-------|
| 1 | mf transaction | 14:34:25 | fail (TargetClosedError) | 0 |
| 2 | xmf_ssnb transaction | 14:36:11 | partial OK (11/12 月) | 247 |
| 3 | xmf_ssnb account | 14:40:44 | **完全ハング** | 0 |
| 4 | xmf_ssnb asset_allocation | 未到達 | — | 0 |

---

## A. crawl_runner reactor 遷移ハング (致命) — [対応済 2206ef9 2026-05-01]

### 対応結果

採用案: **WSL 経由実行への切替** (subprocess 化案は採用せず)。

- `wsl_runner.bat` 新規: Windows から `wsl --cd <wslpath> bash -lc './job_runner.sh ...'` 起動
- `job_runner.sh`: `.venv-wsl/bin/python` 優先 + WSL 検出 (`grep -qi microsoft /proc/version`) 追加
- `.workbench/alias_rules`: `crawl` / `crawl-trans` / `crawl-asset` / `crawl-acct` を `cmd.exe /c wsl_runner.bat` 経由に変更

→ Windows ProactorEventLoop 起因 (plan 仮説 2) を Linux event loop 上実行で回避。
`run_all` の `for inv in invocations: yield runner.crawl(...)` 構造はそのまま維持。
オーバーヘッド: subprocess 化案 (~5s/invocation) より低い。資格情報を CLI argv に
載せる懸念 (plan 旧案の副作用) も発生しない。

### 症状 (記録)

- xmf_ssnb transaction 完了 (14:40:44 `Spider closed (finished)`) 直後に
  account spider が `Spider opened` までは進む。
- 以降 7 時間、 `[scrapy.extensions.logstats] Crawled 0 pages` のみ毎分出力。
- chromium 起動ログ (`Launching browser chromium`) なし。
- spider の `start()` から流れる `_build_login_request` も発火していない
  (login_flow ログ無し)。

### 該当コード

`src/moneyforward_pk/_runner_core.py::run_all` L277-318:

```python
for inv in invocations:
    try:
        crawler = runner.create_crawler(inv.spider_type)
        crawler.signals.connect(_on_spider_closed, signal=signals.spider_closed)
        yield runner.crawl(
            crawler,
            site=inv.site,
            login_user=inv.user,
            login_pass=inv.password,
        )
        stats = captured_stats.pop(inv.spider_type, {})
        results[inv] = _classify_result(inv.spider_type, stats)
    except Exception as exc:
        ...
```

### 原因仮説 (調査結果)

scrapy-playwright の **download handler** は spider opened/closed signals に
ぶら下がる形でブラウザ context を管理しており、 `CrawlerRunner` で同一
reactor 上に **複数 crawler を順次起動**したときに以下のいずれかで詰む:

1. **ScrapyPlaywrightDownloadHandler の context 状態が Crawler 横断で共有**
   され、 1 つ目の crawler 終了時に context を close、 2 つ目の crawler
   起動時に再 open しようとして待機する (deferred が fire しない)。
2. **Twisted asyncio reactor + ProactorEventLoop on Python 3.14** の
   組合せで、 `scrapy-playwright` が抱える別スレッド上の event loop が
   1 個目の crawler shutdown 時に終了し、 2 個目で再起動できない。
3. base spider の `start()` (async generator) が、 1 個目で消費後に
   2 個目で再エントリされる際、 何らかの内部状態を継承して block する。

ログから判別: `Spider opened` まで来ている = `start()` 自体は呼ばれてる
可能性。 `_build_login_request` の log が出てない = yield されたが
download handler に渡ってない = 仮説 (1)/(2) のどちらかが有力。

### 確認すべき事項

- `scrapy-playwright` の changelog で「複数 crawler 順次起動」の制約有無
- `_BrowserLauncher` が crawler スコープか runner スコープか
- 2 個目の `runner.crawl()` が返す Deferred の状態を debugger で観測

### 比較検証結果サマリ (2026-04-29 追記、 引き継ぎ用)

#### 環境前提

両プロジェクトとも **同一マシン**で動作:

- Windows 10 Pro 19045
- Python 3.14.3
- Scrapy 2.15.1
- scrapy-playwright (同 version)
- Twisted 24.11.0 + AsyncioSelectorReactor (Windows ProactorEventLoop)
- chromium (Playwright bundled)

→ **環境差は無い**。

#### 比較対象: `scrapy_smbcnikko_pk` (姉妹 PJ、同実機で動作実績あり)

- 場所: `c:/Users/g/OneDrive/devel/genba-neko@github/scrapy_smbcnikko_pk/`
- 実装: `src/smbcnikko/state_machine/actions.py`, `listing_collection.py`,
  `trading_iteration.py`
- パターン: 1 つの `CrawlerRunner` 上で `yield runner.crawl(c)` を **複数の
  異なる spider class** に対して順次 / 並列で実行
- spider class 例: `ListAccountBalance`, `DepositTransfer`,
  `GenwatashiMarginStock`, `GenbikiMarginStock`,
  `OverorderCorrectionMarginTrade`, `OrderMarginTrade`, `CancelMarginTrade`
- これらが **問題なく動いている** (実運用デーモン)

→ **「異 spider class を 1 reactor で順次起動」自体は scrapy-playwright で動く**。

#### moneyforward_pk のハング症状

E2E 実行ログ (`runtime/logs/moneyforward_pk.log` 14:34〜21:47):

| 時刻 | invocation | 結果 |
|------|-----------|------|
| 14:34:25 | transaction(mf) opened | login fail (TargetClosedError) → 14:34:58 closed |
| 14:36:11 | transaction(xmf_ssnb) opened | login OK → 12 ヶ月分 enqueue → 11/12 月成功 → 14:40:44 closed |
| 14:40:44 | account(xmf_ssnb) opened | **logstats 0 pages のみ 7 時間。 chromium 起動ログなし。 ハング** |
| 21:47 頃 | (reactor.stop で強制終了) | account spider 0 items |

ハング箇所の特定:

- account spider `Spider opened` シグナルは発火 (`scrapy.core.engine` ログあり)
- `JsonArrayOutputPipeline open: path=...` も出力
- 以後 `[scrapy.extensions.logstats] Crawled 0 pages (at 0 pages/min)` が
  毎分出続けるだけ
- `scrapy-playwright Launching browser chromium` が **1 回も出ない**
- → **`engine._pull_start_requests` が `account spider.start()` を消費して
  いない or 消費しても download handler に届いていない**

#### 排除済みの仮説 (コード調査で反証)

| 仮説 | 反証根拠 |
|------|----------|
| 環境差 (Python / scrapy version) | smbcnikko_pk と同マシン同 version |
| scrapy-playwright が複数 crawler 順次起動を非対応 | smbcnikko_pk が同パターンで動く |
| 異 spider class 切替が一般的に NG | smbcnikko_pk が複数異 class で動く |
| `setup_common_logging()` 副作用 | `_CONFIGURED_FLAG` で冪等 (utils/logging_config.py L23-24) |
| middleware の signal hook | moneyforward_pk middlewares に signal 接続なし |
| `JsonArrayOutputPipeline.close_spider` ハング | 同期 file flush + close のみ |
| `SlackNotifierExtension.spider_closed` ハング | 同期 HTTP だが 1 つ目 close 後の処理なので 3 つ目 open に影響しない |
| `SessionManager` crawler 横断共有 | `from_crawler` で毎回新規 instance |
| `runner.create_crawler(string)` の lookup 問題 | string 指定でも 1 つ目は動いてる |

#### 残った仮説 (コード trace では決定不可)

| # | 仮説 | 必要な実機調査 |
|---|------|-----------------|
| 1 | scrapy 2.15.1 engine の `_pull_start_requests` が **2 個目以降の crawler の `async def start()` を消費しない** | scrapy/core/engine.py に print 注入、 または `print` を spider.start() の冒頭に入れて呼ばれてるか確認 |
| 2 | scrapy-playwright の `_browser` instance / `_browser_launched` flag が 1 つ目 crawler の close で完全に reset されず、 2 つ目で再 launch しない | scrapy_playwright/handler.py の `_BrowserManager` 状態を log |
| 3 | spider 切替 (transaction→account) で、 何らかの **moneyforward_pk 固有の per-spider 状態** が 1 つ目から 2 つ目に持ち越されて block | invocation の前後で `gc` の reachable set を比較 |
| 4 | `playwright_context_kwargs={"storage_state": path}` の inject + 別 spider class の組合せ | account spider 単発で `--site xmf_ssnb -a use_storage=true` 等で再現させる |

仮説 1 が最有力 (chromium 起動ログが無い = request が出てない = start() pull
してない可能性大)。

#### 具体的な moneyforward_pk vs smbcnikko_pk 差分 (調査担当向け)

引き継ぎ調査で「smbcnikko_pk にあって moneyforward_pk にない / 逆」を一つずつ
無効化して再現するなら、 以下が候補:

| ファイル | 差分 |
|---------|------|
| `_runner_core.py::run_all` | smbcnikko は `state_machine` 経由でラップ、 moneyforward は inline で `for inv in invocations: yield runner.crawl(...)` |
| `_runner_core.py::run_all` 引数 | moneyforward は `runner.crawl(crawler, site=..., login_user=..., login_pass=...)` で **kwargs 多数**、 smbcnikko は `runner.crawl(crawler, **opt_kwargs)` |
| `create_crawler` 引数型 | moneyforward は string (`inv.spider_type`)、 smbcnikko は class (`action.spider_cls`) |
| middleware セット | moneyforward: `HtmlInspector + PlaywrightSession` のみ。 smbcnikko: `HtmlInspector + MaintenanceGuard + PlaywrightSession + SMBCNikkoPersistentSession` |
| pipeline | moneyforward: `JsonArrayOutputPipeline` (PR #47 新規). smbcnikko: `DynamoDbPipeline` |
| extension | moneyforward: `SlackNotifierExtension` (`spider_closed` signal 接続あり). smbcnikko: なし |
| spider `start()` | 両者 `async def start(): yield scrapy.Request(...)` パターン。 構造的差異なし |
| spider `__init__` | moneyforward `MoneyforwardBase.__init__` は `site` kwarg → variant 解決 + SessionManager hook (`from_crawler`)。 smbcnikko は `prep_start_requests()` 抽象メソッド経由 |
| storage_state inject | 両者 `meta["playwright_context_kwargs"]={"storage_state": path}` で同じ |

注: middleware/pipeline/extension の hang factor は個別に読んだ限り発見でき
なかった (反証済仮説参照)。 が、 「読み損ねている可能性」 は残る。

#### 最低限の再現手順

1. `feat/40_variant_orchestrator` ブランチを checkout
2. `config/accounts.yaml` に xmf_ssnb 1 アカウントだけ書く (mf は外す)
3. `cd src; python -m moneyforward_pk.crawl_runner --site xmf_ssnb`
4. `runtime/logs/moneyforward_pk.log` を tail
5. transaction spider 完了後、 account spider が opened して以降
   `Crawled 0 pages` のみで進まない状態を確認

#### 実用回避策 (#40 PR 進める場合)

各 invocation を **subprocess** で起動:

```python
# crawl_runner.py
import subprocess, sys
for inv in invocations:
    cmd = [
        sys.executable, "-m", "scrapy", "crawl", inv.spider_type,
        "-a", f"site={inv.site}",
        "-a", f"login_user={inv.user}",
        "-a", f"login_pass={inv.password}",
    ]
    subprocess.run(cmd, check=False)
```

reactor / scrapy-playwright 状態が完全に独立するためハングしない。
オーバーヘッドは 1 invocation あたり ~5s (Python 起動 + scrapy 初期化)。
ただし `login_user` / `login_pass` を CLI argv に載せるとプロセス一覧で
見えてしまうので、 環境変数渡しに変更必要。

### 実装案 (a)

`_runner_core.py::run_all` を破棄し、 `crawl_runner.py::main` から
`subprocess.run(["python", "-m", "scrapy", "crawl", spider_type,
"-a", f"site={inv.site}", ...])` を順次実行する形に切替。
出力 JSON 配列の `[ ... ]` 統合は initialize/finalize で対応済なので
そのまま流用可能。

---

## B. summarize() 誤集計 — [対応済 staged 2026-05-01, 未 commit]

### 対応結果

採用案: `summarize(results, elapsed_sec, invocations=None)` に第 3 引数追加。
`invocations` 渡された場合 `results.get(inv, "failed: NotCompleted")` で未完了集計。
`crawl_runner.py::_run` 側も `summarize(results, elapsed, invocations)` に変更。
test `test_summarize_marks_missing_planned_invocations_failed` 追加 / pass。

(plan 旧案の `pending` 先登録方式は採らず、 summarize 側で集計時に補完する形に変更)

### 症状 (記録)

実 3 invocation 走ったのに Summary は `Total: 1 / Succeeded: 1 / Failed: 0`。
mf transaction の fail も account ハングも検知されない。

### 該当コード

`_runner_core.py::summarize` L205-232:

```python
def summarize(results, elapsed_sec):
    total = len(results)
    succeeded = sum(1 for s in results.values() if s == "succeeded")
    failed = {
        f"{inv.site}_{inv.spider_type}_{inv.user}": status
        for inv, status in results.items()
        if status != "succeeded"
    }
    return {"total": total, "succeeded": succeeded, "failed": failed, ...}
```

`run_all` 内 (L302-316) は **for loop の途中で hang したら次 invocation を
登録しないまま停止** し、 `total = len(results)` は実行済み件数しか数えない。

### 原因

- ハングしてる Issue A が根本原因
- だが summarize ロジック自体も「実態」を反映できていない
  - hang した invocation は `results` に未登録 → カウントされない
  - 計画件数 (= `len(invocations)`) を Summary が知らない

### 対応方針

run_all 開始時に **全 invocation を `"pending"` で登録**:

```python
for inv in invocations:
    results[inv] = "pending"

for inv in invocations:
    try:
        ...
        results[inv] = _classify_result(...)   # 上書き
    except Exception:
        results[inv] = f"failed: {exc.__class__.__name__}"
```

`summarize` で `pending` も failed として集計 (`failed: not_run` 等):

```python
succeeded = sum(1 for s in results.values() if s == "succeeded")
failed = {
    f"{inv.site}_{inv.spider_type}_{inv.user}": (status if status != "pending" else "failed: not_run")
    for inv, status in results.items()
    if status != "succeeded"
}
```

Issue A 解決後でも、 何か別要因で途中停止した時の検知に有用。

---

## D. typed run で他種別 JSON 出力が truncate される — [対応済 2a837a7 2026-05-01]

### 症状 (記録)

`crawl_runner --type transaction` 等の typed run で、 `initialize_output_files`
が常に 3 種別 (`transaction` / `account` / `asset_allocation`) すべてを `[`
で truncate していたため、 直前 run で取得済の他種別 JSON が消失。

### 対応結果

- `initialize_output_files(output_dir, spider_types=None)` / `finalize_output_files(...)`
  に `spider_types` 引数追加。 `None` 時は従来通り 3 種別、 指定時は対象のみ touch
- `_target_spider_types()` ヘルパ追加 (重複排除 + 未知種別を `KeyError`)
- `crawl_runner.py::_run`: `target_spider_types = tuple(dict.fromkeys(inv.spider_type for inv in invocations))`
  を算出し initialize/finalize に渡す
- test 31 件相当を `test_crawl_runner_unit.py` に追加 (spider types フィルタ)

---

## C. transaction 月切替 timeout (2025/10 で発生、データ欠損) — [対応済 staged 2026-05-01, 未 commit]

### 対応結果

採用案 1: `:visible` pseudo + `wait_for(state="visible")` で重なり回避。

`spiders/transaction.py::parse_month` の月クリックを以下に置換:

```python
month_li = p.locator(
    f'li[data-year="{year}"][data-month="{month}"]:visible'
)
await month_li.wait_for(state="visible", timeout=10_000)
await month_li.click(timeout=10_000)
```

副次対応として、 click 失敗時に `{name}/months_failed` カウンタ bump (silent skip
検知)。 `_classify_result` が同カウンタを `failed: PartialMonthFetch` に分類。

test 3 件追加 / 既存 1 件更新 (page.locator mock 化):
- `test_parse_month_yields_items_after_switcher_succeeds` (locator 経路に更新)
- `test_parse_month_aborts_when_switcher_throws` (months_failed bump 検証追加)
- `test_parse_month_aborts_when_visible_month_locator_times_out` (新規)
- `test_classify_result_marks_months_failed_as_partial` (新規)



### 症状

xmf_ssnb transaction で `2025/10` の月切替時に 30 秒 timeout。
他 11 月分は成功。データ 1 ヶ月分欠損 (約 25 件想定)。

### ログ抜粋

```
Month switcher failed (2025/10): Page.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("li[data-year=\"2025\"][data-month=\"10\"]")
  - locator resolved to <li data-month="10" data-year="2025" ...>
  - attempting click action
  - element is visible, enabled and stable
  - scrolling into view if needed
  - <li data-month="9" data-year="2024" ...> from <li data-year="2024" ...>
    subtree intercepts pointer events
  - retrying click action
  - element is not visible
  ...
```

### 該当コード

`src/moneyforward_pk/spiders/transaction.py::parse_month` L67-86:

```python
async with managed_page(page) as p:
    await p.wait_for_load_state("domcontentloaded")
    try:
        await p.click(".fc-button-selectMonth", timeout=30_000)
        await p.click(f'li[data-year="{year}"]', timeout=30_000)        # 年クリック
        await p.click(
            f'li[data-year="{year}"][data-month="{month}"]',            # 月クリック
            timeout=30_000,
        )
        await p.wait_for_load_state("networkidle")
    except Exception as exc:
        self.logger.warning(...)
        return
```

### 原因

月選択 UI:
- 年プルダウン展開後、対象年の月プルダウンが描画される
- 同じ DOM 上に **前年・別年の月項目**も `<li data-year="..." data-month="...">`
  として存在しうる (コンポーネントが履歴的に DOM に残す or アニメ中)
- playwright の locator は **target 要素を見つけたが、 そのスクロール位置に
  別年の li が重なって pointer event を吸う** ため click できず
- retry も element-is-not-visible になり失敗

### 対応方針

#### 案 1: 月クリック前に対象 li が visible になるまで wait

```python
await p.click(f'li[data-year="{year}"]', timeout=30_000)
month_li = p.locator(
    f'li.spec-fc-button-click-attached'
    f'[data-year="{year}"][data-month="{month}"]:visible'
)
await month_li.wait_for(state="visible", timeout=10_000)
await month_li.click(timeout=10_000)
```

`:visible` pseudo で見えてる li のみ取得。 (playwright は `:visible` 対応)。

#### 案 2: force click / position click

```python
await p.click(
    f'li[data-year="{year}"][data-month="{month}"]',
    timeout=30_000,
    force=True,    # 重なってる要素を無視して click イベント発火
)
```

`force=True` は visibility check をスキップ。 ただし event handler 側が
ちゃんと反応するかは UI 依存。

#### 案 3: keyboard / API ナビゲーション

URL に month=YYYYMM パラメータを付けて直接遷移 (transactions_url が month
クエリ受けるなら)。 月切替 UI を完全に回避できる。

→ **案 1 を第一候補、 ダメなら案 2、 最後に案 3** 推奨。

### 副次対応 (#44 関連) — [部分対応 staged 2026-05-01, 未 commit]

`Month switcher failed` は warning + `return` で **silent skip** される
=  Issue B の results では `succeeded` 扱いになる。 これも要修正。

#### 採用結果

`_classify_result` に **PlaywrightError 検知**を追加 (staged):

- `{spider_type}/playwright/errback` カウンタ > 0 → `failed: PlaywrightError`
- `downloader/exception_type_count/playwright.*` > 0 → `failed: PlaywrightError`

test 2 件追加 / pass:
- `test_classify_result_marks_playwright_errback_failed`
- `test_classify_result_marks_playwright_downloader_exception_failed`

(plan 旧案の `{name}/months_failed` 専用カウンタは未実装。 月切替 timeout が
playwright errback を踏むなら現行検知で拾える前提。 spider 側で warning skip して
errback を踏まない経路の場合は別途 stats 追加が必要 → C 本体修正と合わせて再検討)

---

## まとめ: PR #40 / Issue #40 への影響

### 進捗 (2026-05-01 時点)

| # | 内容 | 状態 | commit |
|---|------|------|--------|
| A | reactor 遷移ハング | **対応済** (WSL 経由実行で回避) | 2206ef9 |
| B | summarize() 誤集計 | **対応済 (staged)** (`invocations` 引数追加) | 未 commit |
| C 副次 | silent skip 検知 | **対応済** (PlaywrightError + months_failed 検知) | 05892f8 + staged |
| C 本体 | 月切替 click intercept | **対応済 (staged)** (`:visible` 待機) | 未 commit |
| D | typed run で他種別 JSON 上書き | **対応済** | 2a837a7 |

### 残 task

- [ ] staged 分 (C 本体 + months_failed 検知) を commit
- [ ] WSL 経路で E2E 再実行 → orchestrator 完走確認 (2025/10 含 12 ヶ月取得)
- [ ] 完走確認後 PR #47 を ready for review に切替

### 完了済 task

- [x] A: WSL 経由実行に切替 (2206ef9)
- [x] B: `summarize()` に `invocations` 引数追加 + test (05892f8)
- [x] C 副次: `_classify_result` に PlaywrightError 検知 + test 2 件 (05892f8)
- [x] C 本体: `parse_month` を `:visible` 待機に + months_failed 検知 (staged)
- [x] D: `initialize/finalize_output_files` に `spider_types` 引数 (2a837a7)
