# Phase 7: README + .env.example + ランナースクリプト

実施日時: 2026-04-25 05:30 JST
所要: 約5分
コミット: `a2d57ff`

## 目的
セットアップ手順 + 実行スクリプト + 環境変数テンプレートを整備し,
クリーン環境からの再現性を担保。

## 実施内容

### 1. `.env.example`
全環境変数を網羅:
- MoneyForward 認証 (`SITE_LOGIN_USER` / `SITE_LOGIN_PASS` / `SITE_LOGIN_ALT_USER`)
- `SITE_PAST_MONTHS=12`
- Playwright (`MONEYFORWARD_HEADLESS`, `MONEYFORWARD_LOGIN_MAX_RETRY`)
- DynamoDB (空なら pipeline 自動無効)
- AWS 認証
- `SLACK_INCOMING_WEBHOOK_URL` (空で noop)
- `LOG_LEVEL` / `LOG_FILE_ENABLED` / `LOG_FILE_PATH`

### 2. `job_runner.sh` (WSL/Linux/macOS)
- `set -euo pipefail` 厳格モード
- `.env` 自動 source (存在時)
- `.venv-win/Scripts/python.exe` 優先, fallback `python`
- サブコマンド: `transaction|trans|asset|allocation|account|accounts`
- `cd src && exec python -m scrapy crawl <spider>`

### 3. `job_runner.bat` (Windows)
- `.env` を `for /f` でパース (`#` 行除外)
- `%ROOT%.venv-win\Scripts\python.exe` 優先
- 同サブコマンド体系
- `cd %ROOT%src && python -m scrapy crawl %SPIDER%`

### 4. `README.md` 全面書き換え
- 概要 (旧 Splash → Playwright 移行説明)
- 前提 (Python 3.10+, Playwright Chromium, 任意で AWS/Slack)
- セットアップ手順 (venv, pip, playwright install, .env)
- 実行例 (Windows / WSL / 直接 scrapy)
- ヘッドレス無効化 tip
- スパイダー一覧 (3 種)
- ディレクトリ構造
- テスト実行手順
- 主要設計判断 (`PLAYWRIGHT_CONTEXTS={}` 空意図 etc.)
- 改善余地 (xmf_* 具象, 2FA, storage_state 永続化, etc.)

### 5. `runtime/.gitkeep` (.gitignore で追跡されないため commit 対象外)

## 検証
- `git log --oneline` で 7 コミット確認
- 最終 pytest: 25 passed
- 最終 `scrapy list`: 3 spider 認識

## 学び・判断
- Windows / WSL 両対応のため `.bat` + `.sh` 両方提供
- `.env.example` は smbcnikko_pk 流に「全変数列挙 + コメント説明」
- README は構造説明 + 設計判断 + 改善余地まで含めて自己完結化
