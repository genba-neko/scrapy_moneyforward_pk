# Phase 3: Utils / Middlewares

実施日時: 2026-04-25 04:52 JST
所要: 約5分
コミット: `535328c` (合算)

## 目的
スパイダー横断の共通機能を分離。Playwright meta 構築, ログイン状態検知,
セッションリトライミドルウェア, ログ整備。

## 実施内容

### 1. `utils/playwright_utils.py`
- `init_page_block_static(page, request)` — image/font/media/stylesheet 遮断で高速化
- `build_playwright_meta(*, include_page, page_methods, context, extra)` —
  全 Playwright リクエストの meta を一元化
- `managed_page(page)` async context manager — `unroute("**/*")` + `close()` 保証

### 2. `utils/logging_config.py`
- `setup_common_logging()` 冪等
- 設定キー優先順: 引数 > 環境変数 > デフォルト
- `LOG_FILE_ENABLED=true` で `TimedRotatingFileHandler` (midnight, backupCount=14)
- boto3/botocore/urllib3/s3transfer を WARNING 抑制
- `_moneyforward_pk_logging_configured` フラグで二重設定防止

### 3. `utils/slack_notifier.py`
- `SlackNotifier(webhook_url)` クラス
- webhook 未設定 → noop (debug log のみ)
- import 失敗時も握りつぶし (CI で slackweb 入っていない可能性)

### 4. `utils/session_utils.py`
- `is_login_url(url)` — `/sign_in` / `/users/sign_in` 系 regex
- `is_session_expired(response)` — URL + title `ログイン` 判定

### 5. `middlewares/__init__.py`
- `PlaywrightSessionMiddleware` を再エクスポート

### 6. `middlewares/playwright_session.py`
- `process_response`: Playwright レスポンスかつ session 失効 → リクエスト再発行
- `login_retry_times` カウンタ管理, `MONEYFORWARD_LOGIN_MAX_RETRY` で打ち切り
- `dont_filter=True` + `moneyforward_force_login=True` 付与
- スタッツ: `<spider>/session/retry`, `<spider>/session/expired_final`

## 学び・判断
- 静的アセット遮断は smbcnikko_pk 流 (帯域 + 時間節約)
- `is_session_expired` を純関数化 → middleware と spider 両方からテスト可能
- `slackweb` 依存をオプショナル扱い → `SLACK_INCOMING_WEBHOOK_URL` 空で完全 noop
