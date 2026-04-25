# scrapy_moneyforward_pk 再構築計画

日付: 2026-04-25
元: scrapy_moneyforward (Scrapy + Splash + Lua)
参考: scrapy_smbcnikko_pk (Scrapy + Playwright, src/ layout)

## 目的
Splash/Lua依存を撤廃、Scrapy + Playwrightへ完全置換。smbcnikko_pk同等の構造品質。

## スコープ
- moneyforward.com本体 (mf_transaction / mf_asset_allocation / mf_account)
- パートナーポータル (xmf_*) はサブクラス拡張ポイントとして設計のみ (v1未実装)
- 状態機械/パスキー/デーモン (smbcnikko固有) は不要 → 省略
- 2FA非対応 (元プロジェクトも未対応)

## アーキテクチャ
```
scrapy_moneyforward_pk/
├── src/
│   ├── scrapy.cfg
│   └── moneyforward_pk/
│       ├── settings.py             # Playwright wiring, .env
│       ├── items.py                # Transaction / AssetAllocation / Account
│       ├── pipelines.py            # DynamoDbPipeline (元と互換)
│       ├── middlewares/
│       │   └── playwright_session.py   # 再認証
│       ├── spiders/
│       │   ├── base/moneyforward_base.py  # login + errback共通
│       │   ├── _parsers.py         # HTML → Item (純関数)
│       │   ├── transaction.py      # /cf 月別
│       │   ├── asset_allocation.py # /bs/portfolio
│       │   └── account.py          # /accounts (更新ボタン + リトライ)
│       └── utils/
│           ├── playwright_utils.py
│           ├── logging_config.py
│           ├── slack_notifier.py
│           └── session_utils.py
├── tests/
├── .env.example
├── requirements.txt
├── pyproject.toml
├── job_runner.bat / .sh
└── README.md
```

## Playwright置換表
| 元 (Lua) | 先 (Playwright) |
|---------|----------------|
| `splash:go(url)` | `await page.goto(url)` |
| `splash:wait(n)` | `await page.wait_for_timeout(n*1000)` |
| `splash:select('sel'):click()` | `await page.click('sel')` |
| `form:fill({k=v})` + `form:submit()` | `await page.fill('sel', v)` + `await page.click('submit')` |
| `splash:init_cookies(c)` | BrowserContext自動維持 |
| `SplashRequest(lua=...)` | `Request(meta={"playwright": True, ...})` |

## 環境変数 (元互換維持, SPLASH_URL除去)
- `SITE_LOGIN_USER`, `SITE_LOGIN_PASS`, `SITE_LOGIN_ALT_USER`, `SITE_PAST_MONTHS`
- `AWS_*`, `DYNAMODB_TABLE_NAME`, `DYNAMODB_BATCH_N`, `DYNAMODB_PUT_DELAY`
- `SLACK_INCOMING_WEBHOOK_URL`
- `LOG_LEVEL`, `LOG_FILE_ENABLED`, `LOG_FILE_PATH`
- 新規: `MONEYFORWARD_HEADLESS`, `MONEYFORWARD_LOGIN_MAX_RETRY`

## フェーズ
1. スケルトン (plan + requirements + scrapy.cfg)
2. items + settings + pipelines
3. utils + middlewares
4. baseスパイダー + ログイン
5. 3具象スパイダー
6. pytest
7. README + .env.example + job_runner

## 完了判定
- pytest全通
- ruffクリーン
- `scrapy list` で3スパイダー認識
- 手動実行可能

## 2FA・パートナーポータル
v2候補。baseスパイダーの`login_flow`をサブクラスで上書き可能に設計。
