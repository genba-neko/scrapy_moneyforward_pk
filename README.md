# scrapy_moneyforward_pk

MoneyForward クローラ (Scrapy + Playwright)。旧 `scrapy_moneyforward` の
Splash/Lua 依存を撤廃し、`scrapy-playwright` ベースへ完全移行したもの。

参考構造: [`scrapy_smbcnikko_pk`](../scrapy_smbcnikko_pk)。

## 前提

- Python 3.10+
- Playwright 同梱の Chromium
- (任意) AWS DynamoDB、Slack Incoming Webhook

## セットアップ

```powershell
# 1. 仮想環境
python -m venv .venv-win

# 2. 依存インストール
.venv-win\Scripts\pip install -r requirements.txt

# 3. Playwright ブラウザ取得
.venv-win\Scripts\python -m playwright install chromium

# 4. 環境変数
copy .env.example .env
# .env を編集 (SITE_LOGIN_USER / SITE_LOGIN_PASS 等)
```

## 実行

```powershell
# Windows
job_runner.bat transaction
job_runner.bat asset
job_runner.bat account
```

```bash
# WSL / Linux
./job_runner.sh transaction
./job_runner.sh asset
./job_runner.sh account
```

直接実行:

```powershell
cd src
..\.venv-win\Scripts\python -m scrapy crawl mf_transaction
..\.venv-win\Scripts\python -m scrapy crawl mf_asset_allocation
..\.venv-win\Scripts\python -m scrapy crawl mf_account
```

ヘッドレス無効:

```powershell
$env:MONEYFORWARD_HEADLESS="false"
job_runner.bat transaction
```

## スパイダー

| 名前 | 対象 | 出力 Item |
|-----|-----|----------|
| `mf_transaction` | `/cf` (月別) | `MoneyforwardTransactionItem` |
| `mf_asset_allocation` | `/bs/portfolio` | `MoneyforwardAssetAllocationItem` |
| `mf_account` | `/accounts` + 更新ボタン | `MoneyforwardAccountItem` |

## ディレクトリ構造

```
scrapy_moneyforward_pk/
├── src/
│   ├── scrapy.cfg
│   └── moneyforward_pk/
│       ├── settings.py                 # Playwright wiring, .env 読込
│       ├── items.py
│       ├── pipelines.py                # DynamoDbPipeline
│       ├── middlewares/
│       │   └── playwright_session.py   # 再認証
│       ├── spiders/
│       │   ├── base/moneyforward_base.py   # ログイン共通基底
│       │   ├── _parsers.py             # HTML → Item (テスト容易化のため分離)
│       │   ├── transaction.py
│       │   ├── asset_allocation.py
│       │   └── account.py
│       └── utils/
│           ├── playwright_utils.py
│           ├── logging_config.py
│           ├── session_utils.py
│           └── slack_notifier.py
├── tests/                              # pytest (25 tests)
├── plan/
├── .env.example
├── requirements.txt
├── pyproject.toml
├── job_runner.{bat,sh}
└── README.md
```

## テスト

```powershell
.venv-win\Scripts\pytest
```

パーサ・パイプライン・ミドルウェア・設定を単体テスト。Playwright 実通信は
含まない (手動 / E2E は別途)。

## 主要設計判断

- `PLAYWRIGHT_CONTEXTS = {}` 空 — 最初の `Request` が `storage_state` を
  `playwright_context_kwargs` で注入する余地を残すため (smbcnikko_pk と同一方針)。
- `_parsers.py` でパースを純関数化 → HTML fixture だけでテスト可能。
- `DYNAMODB_TABLE_NAME` が空なら pipeline を無効化 → dev/CI で AWS 不要。
- 2FA は非対応 (旧プロジェクトも未対応)。必要なら `MoneyforwardBase.login_flow`
  をサブクラスで上書き。
- パートナーポータル (`*.x.moneyforward.com`) は `XMoneyforwardLoginMixin`
  で拡張可能。v1 では具象スパイダー未提供。

## 改善余地

- パートナーポータル具象スパイダー (xmf_ssnb, xmf_mizuho ほか) の追加
- 2FA (メール/SMS/Authenticator) 対応
- Playwright `storage_state` 永続化によるログインスキップ
- HTML inspector middleware (デバッグ保存) の移植
- 実通信を伴う integration テスト
- Slack 通知の spider_closed フック統合
