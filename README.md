# scrapy_moneyforward_pk

MoneyForward クローラ (Scrapy + Playwright)。旧 `scrapy_moneyforward` の
Splash/Lua 依存を撤廃し、`scrapy-playwright` ベースへ完全移行したもの。

参考構造: [`scrapy_smbcnikko_pk`](../scrapy_smbcnikko_pk)。

## 前提

- Python 3.10+
- Playwright 同梱の Chromium
- (任意) Slack Incoming Webhook

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

スパイダー引数:

```powershell
# 取得月数を引数で上書き (default: SITE_PAST_MONTHS=12)
..\.venv-win\Scripts\python -m scrapy crawl mf_transaction -a past_months=3
```

## 出力

`JsonOutputPipeline` がスパイダーごとに JSON Lines ファイルを書き出す。

- 出力先: `OUTPUT_DIR` (default: `runtime/output/`、プロジェクトルート配下のみ許可)
- ファイル名: `OUTPUT_FILENAME_TEMPLATE` (default: `{spider}_{date:%Y%m%d}.jsonl`)
- 形式: 1 行 1 Item の JSON Lines (`ensure_ascii=False`)
- 同名ファイル衝突時は `-1` `-2` ... のサフィックスで衝突回避

例: `runtime/output/mf_transaction_20260425.jsonl`

## ディレクトリ構造

```
scrapy_moneyforward_pk/
├── src/
│   ├── scrapy.cfg
│   └── moneyforward_pk/
│       ├── settings.py                 # Playwright wiring, .env 読込
│       ├── items.py
│       ├── pipelines.py                # JsonOutputPipeline (JSON Lines)
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
├── tests/                              # pytest (81 tests, coverage 86%)
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
- 出力は JSON Lines 単一バックエンド (`JsonOutputPipeline`)。AWS 不要。
- 2FA は非対応 (旧プロジェクトも未対応)。必要なら `MoneyforwardBase.login_flow`
  をサブクラスで上書き。
- パートナーポータル (`*.x.moneyforward.com`) は `XMoneyforwardLoginMixin`
  で拡張可能。v1 では具象スパイダー未提供。

## 運用

### 定期実行 (GitHub Actions)

`.github/workflows/scrapy-nightly.yml` が毎日 18:00 UTC (JST 03:00) に
`workflow_dispatch` 互換の smoke ジョブを起動する。submodule に依存しない
ため、private workbench submodule の取得失敗で job が止まらない。
本番のクロールは OS のスケジューラから `job_runner.bat` / `job_runner.sh`
を起動する想定で、CI は `scrapy list` での import 健全性確認のみ。

### Slack 通知

`SLACK_INCOMING_WEBHOOK_URL` を設定すると `SlackNotifierExtension` が
`spider_closed` シグナルに購読し、終了理由・取得件数・経過秒を 1 行の
テキストで投稿する。未設定時は extension が `NotConfigured` を投げて
スキップされ、no-op で動作する。

### 出力ローテーション

`JsonOutputPipeline.open_spider` 起動時に `OUTPUT_RETENTION_DAYS`
(default 14、env で上書き) を超過した同一スパイダーの jsonl ファイルを
削除する。他スパイダーのファイルは保持される。`0` を指定すると
ローテーション無効。

### セッション切れ時の再ログイン

`PlaywrightSessionMiddleware` は `/sign_in` 等のログイン URL/タイトルを
検出すると `meta["moneyforward_force_login"]=True` を立て、対象 Request
を `MoneyforwardBase.handle_force_login` に渡す。これが
`_build_login_request(follow_up=...)` を経由して新しいログイン試行を
Request 化し、ログイン成功後に元の Request を再生する。再認証が
発生したら stats counter `<spider>/login/forced` が 1 加算される。

## セキュリティ

- `paths.resolve_output_dir` は `is_relative_to(PROJECT_ROOT)` で
  PROJECT_ROOT の外を指す `OUTPUT_DIR` を `ValueError` で拒否する。
  シンボリックリンクや `..` を含むパスは `Path.resolve` で吸収。
- `paths.sanitize_spider_name` は `[A-Za-z0-9_-]` 以外を `_` に置換し、
  `..` や `/` を含むスパイダー名でも安全な出力ファイル名を生成する。
- 認証情報 (`SITE_LOGIN_USER` / `SITE_LOGIN_PASS`) は `.env` から
  load_dotenv で読み込まれ、コミット禁止 (`.gitignore` 推奨)。
  `pytest` 実行時はモジュール import 時の load_dotenv をスキップして
  シェル env が漏れないようにしている。

## 改善余地

- パートナーポータル具象スパイダー (xmf_ssnb, xmf_mizuho ほか) の追加
- 2FA (メール/SMS/Authenticator) 対応
- Playwright `storage_state` 永続化によるログインスキップ
- HTML inspector middleware (デバッグ保存) の移植
- 実通信を伴う integration テスト
