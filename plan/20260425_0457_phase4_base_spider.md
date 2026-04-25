# Phase 4: Base Spider + Login Flow

実施日時: 2026-04-25 04:57 JST
所要: 約8分
コミット: `535328c` (合算)

## 目的
Splash Lua のログインスクリプトを Playwright async coroutine に置換。
`MoneyforwardBase` が共通基底, パートナーポータル用 `XMoneyforwardLoginMixin`
で拡張可能に。

## 実施内容

### 1. `spiders/base/__init__.py`
空ファイル。

### 2. `spiders/base/moneyforward_base.py`

#### クラス階層
- `MoneyforwardBase(scrapy.Spider)` — 基底
- `XMoneyforwardLoginMixin` — `*.x.moneyforward.com` 用 (login flow override)

#### 属性
- `start_url = "https://moneyforward.com/"`
- `is_partner_portal = False`
- `login_timeout_ms = 60_000`

#### コンストラクタ + `from_crawler`
- `-a login_user=... -a login_pass=...` を受理
- 未指定なら `SITE_LOGIN_USER` / `SITE_LOGIN_PASS` 設定から取得
- 両方空時は警告ログ

#### Entry
- `async def start()` (Scrapy 2.13+ 流) — 1 リクエスト yield
- `def start_requests()` (旧スクレイピー互換)
- `_build_login_request()` ヘルパで Playwright meta + `include_page=True`

#### Login Flow (`async def login_flow(page)`)
moneyforward.com 用 default 実装。
1. `domcontentloaded` 待機
2. top → `a[href="/sign_in"]` クリック (存在時)
3. → `a[href^="/sign_in/email"]` クリック (存在時)
4. `input[name="mfid_user[email]"]` fill → submit
5. 別ページの password fill → submit
6. `networkidle` 待機

#### `_parse_after_login(response)` 共通フロー
1. `playwright_page` 取得
2. `managed_page` で安全に閉じる context
3. `login_flow(p)` 呼び出し, 失敗→stats 計上 + 早期 return
4. `p.url` / `p.title()` ログ
5. `p.content()` で HTML 取得
6. `response.replace(url, body)` で Scrapy `HtmlResponse` 化
7. `is_session_expired` チェック
8. 通過なら `after_login(response)` 経由でサブクラスへ移譲

#### `_iter_after_login` ブリッジ
- `after_login` が同期 generator / async generator どちらでも動く

#### Hooks (オーバーライド対象)
- `login_flow(page)` — ログイン UI 操作
- `after_login(response)` — 認証後リクエスト群

#### Errback
- `errback_playwright(failure)` — log + stats + page.close()

#### `XMoneyforwardLoginMixin`
- `*.x.moneyforward.com` の `sign_in_session_service[email/password]` フォーム対応
- `login_flow` のみ override

### 3. ヘルパ追加 (Phase 6 修正で追加)
- `_inc_stat(key, count)` — `crawler.stats` Optional 安全アクセス

## 学び・判断
- `async def start()` (新) と `start_requests()` (旧) の両対応で Scrapy
  2.x / 2.13+ どちらでも動作
- Lua の `splash:select():click()` を Playwright `locator(...).first.click()` に置換
- パスワードフィールド名にゆれ (`mfid_user[password]` or `input[type=password]`)
  → カンマ区切りで両対応
- `managed_page` で Playwright リソース漏れ防止
