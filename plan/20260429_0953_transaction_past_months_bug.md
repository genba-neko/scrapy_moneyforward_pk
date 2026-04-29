# MfTransactionSpider 12 ヶ月取得バグ 調査・修正プラン (Issue #44)

作成: 2026-04-29 09:53
Issue: #44
ブランチ: `fix/44_transaction_past_months` (master ベース)

## 背景

`SITE_PAST_MONTHS=12` 設定で `xmf_ssnb_transaction` を実行しても、
当月分 1 ヶ月のみ取得して終了する。

実ログ (2026-04-28 #43 PR の E2E 検証中に判明):
```
xmf_ssnb_transaction/login/skipped: 1
xmf_ssnb_transaction/login/success: 1
xmf_ssnb_transaction/months_fetched: 1
xmf_ssnb_transaction/output/items: 65
scheduler/enqueued: 2  (= login req + 1 month req)
_parse_after_login: returning 1 follow-up items/requests
```

`_parse_after_login` の list-return 化 (#43 で対応済) では解消しなかった。
yield 元 (`MfTransactionSpider.after_login`) で 1 件しか出ていない。

過去報告「2 ページしか取れない」も同根の可能性が高い。

## 現状コード

```python
# src/moneyforward_pk/spiders/transaction.py
class MfTransactionSpider(MoneyforwardBase):
    def __init__(self, *args, past_months=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.past_months = int(past_months) if past_months is not None else None

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider.past_months is None:
            spider.past_months = crawler.settings.getint("SITE_PAST_MONTHS", 12)
        return spider

    async def after_login(self, response):
        today = date.today()
        months = self.past_months if self.past_months is not None else 12
        for offset in range(months):
            target = today - relativedelta(months=offset)
            yield self._month_request(target.year, target.month)
```

```python
# src/moneyforward_pk/spiders/base/moneyforward_base.py L373-379
results: list = []
async for item_or_request in self._iter_after_login(post_login):
    results.append(item_or_request)
self.logger.info("_parse_after_login: returning %d follow-up items/requests", len(results))
return results

async def _iter_after_login(self, response):
    result = self.after_login(response)
    if result is None:
        return
    if hasattr(result, "__aiter__"):
        async for x in result:
            yield x
    else:
        for x in result:
            yield x
```

## 仮説 (調査前)

| # | 仮説 | 検証結果 |
|---|------|---------|
| A | `past_months` が 1 に上書きされている (env/getint 経路) | **確定** |
| B | `for offset in range(months)` 内で 1 yield 後に silent 例外 | 否定 (yielded=1, expected=1 で正常終了) |
| C | `_iter_after_login` の async-iter ブリッジが 1 件で打ち切られる | 否定 |
| D | scrapy 側が coroutine 戻り値 list の 1 件目しか processed していない | 否定 |
| E | Python 3.14 + scrapy 2.15 + async gen の組合せバグ | 否定 |

## 真因

debug log で確認した結果:

```
[DEBUG #44] settings.py raw SITE_PAST_MONTHS='1'
  env_keys_with_PAST_or_MONTH={'SITE_PAST_MONTHS': '1'}
```

`os.environ["SITE_PAST_MONTHS"]` が settings.py import 時点で **既に '1'** で
存在していた。`.env` の `SITE_PAST_MONTHS=12` は `load_dotenv(override=False)`
により無視されていた。

env に '1' が注入された経路:

- `workbench/scripts/profile.ps1::Import-Env` (L295-311) が VS Code PowerShell
  terminal 起動時に `.env` を行ごと読んで `[System.Environment].SetEnvironmentVariable(key, value, 'Process')` で env var をセットする。
- これは **terminal 起動時 1 回のみ** 実行される。
- `.env` を後から書き換えても env は古い値のまま。
- 過去 user が `.env` に `SITE_PAST_MONTHS=1` を書いた状態で terminal を起動 →
  profile.ps1 が env=1 注入。
- その後 user が `.env` を `12` に書き換えたが、terminal の env は依然 1。
- `python -m scrapy crawl` 起動 → settings.py の `load_dotenv(override=False)` が
  既存 env (=1) を尊重 → settings.py 内の `SITE_PAST_MONTHS=1` 確定 →
  spider に 1 流入。

## 修正

`src/moneyforward_pk/settings.py`:

```python
# Before:
load_dotenv(PROJECT_ROOT / ".env", override=False)
# After:
load_dotenv(PROJECT_ROOT / ".env", override=True)
```

`.env` を **真実値**として扱う。terminal 再起動なしでも `.env` 編集が反映される。

## 検証

- ruff clean
- pytest 257 pass
- E2E (2026-04-29 13:01):
  - `_parse_after_login: returning 12 follow-up items/requests`
  - `scheduler/enqueued: 13` (= login req + 12 month req)
  - `xmf_ssnb_transaction/months_fetched: 12`
  - `item_scraped_count: 1025`
  - `finish_reason: finished`

## 影響範囲

- `src/moneyforward_pk/settings.py` (`load_dotenv(override=True)` のみ)

## 残作業

- [完了] 仮説確定 (debug log 経由) → 真因 = profile.ps1 + override=False の組合せ
- [完了] 修正実装 (`override=True`)
- [完了] E2E 検証 (12 ヶ月 / 1025 items / finished)
- [ ] commit / push / PR / merge

## 副次的な気づき

- `workbench/scripts/profile.ps1::Import-Env` の挙動を CLAUDE.md などに
  「`.env` 編集後は terminal 再起動 もしくは `Import-Env` 再呼出が必要」
  として記録するのが望ましいが、`override=True` で本質的に問題は解消するため
  本 PR では追記しない。必要があれば別 PR で運用ルール文書化する。
- ユニットテスト: 真因が settings 経路 (env 経由) のため spider 層の単体
  テストでは再現不能。既存の `test_transaction_spider_unit.py` で
  `past_months=12` → 12 件 yield のロジックは既に担保されている。
