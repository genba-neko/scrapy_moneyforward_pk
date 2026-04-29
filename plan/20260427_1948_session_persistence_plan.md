# Session 永続化実装プラン (Issue #43)

作成: 2026-04-27 19:48
Issue: #43
ブランチ: `feat/43_session_persistence` (master ベース)

## 背景

Issue #40 (orchestrator) を実装したが、Playwright session 永続化機構がなく
spider 起動毎にゼロからログインしていた。これが以下の問題を起こしていた:

- 起動毎に毎回 login_flow → 過剰ログインで bot 検出/レート制限ヒット (403)
- 同 account に対する短時間多数ログイン
- 各起動で 5〜10 秒のログインオーバーヘッド

参考: `scrapy_smbcnikko_pk` には `PasskeySessionManager` で storage_state 永続化機構が完備。これを ID/PW 認証用に簡素化して移植する。

## 調査結果

### 1. login_flow セレクタの既存バグ

`spiders/base/moneyforward_base.py` の `XMoneyforwardLoginMixin.login_flow`:

```python
entry = page.locator('a[href="/users/sign_in"]').first  # 完全一致
```

ユーザー提供の fixture (`data/fixutres_source/01. トップページ/`) で
実 HTML 確認:

```html
<a rel="nofollow" href="https://ssnb.x.moneyforward.com/users/sign_in">ログイン</a>
```

href が **絶対 URL** のため `[href="/users/sign_in"]` は never match。
silent skip されて email フォーム fill に直行 → top page にフォーム無く timeout。

→ 一致していない。`a[href$="/users/sign_in"]` (suffix match) で修正。
リンクが見つからない場合は `page.goto("/users/sign_in")` で直接遷移する fallback も追加。

### 2. fixture データから判明した DOM 構造 (xmf_ssnb)

| ページ | URL | 主な特徴 |
|---|---|---|
| トップ (未ログイン) | `https://ssnb.x.moneyforward.com/` | `body class="before-login"`, ログインリンクは絶対URL |
| ログインページ | `https://ssnb.x.moneyforward.com/users/sign_in` | email/password 同一ページ (1 page form), `name="sign_in_session_service[email]"` |
| ログイン後 | `https://ssnb.x.moneyforward.com/` | `<a href=".../users/sign_out">ログアウト</a>` 存在 |
| 家計 | `/cf` | (4412行) |
| 資産 | `/bs/portfolio` | (377行) |

主要差分: ログインページは **1 ページに email + password** 同居 (mf 本体は 2 ページ分割)。

### 3. session 検出の妥当性

`is_session_expired` 既存: URL に `/sign_in` 含む or title に "ログイン" 含む。
top page の場合は両条件 False → expired と判定されない (top page 自体は valid)。
実際の検出は **logout link 存在** (`a[href*="/sign_out"]`) で行う方が確実。

### 4. smbcnikko_pk PasskeySessionManager との API 比較

| smbcnikko (PasskeySessionManager) | moneyforward (SessionManager) |
|---|---|
| `has_saved_session()` | `has_saved_session()` ✓ 揃え |
| `get_storage_state()` | `get_storage_state()` ✓ 揃え |
| `invalidate_session()` | `invalidate_session()` ✓ 揃え |
| `is_session_valid()` (sync_playwright で再検証) | 持たない (オーバーヘッド大) |
| `ensure_session()` (passkey 同期実行) | 持たない (login は async scrapy-playwright) |
| `refresh_session()` | 持たない |
| (なし) | `save_from_context(context)` async |

→ **storage_state 連携 API** は完全互換、**認証実行ロジック**は方式違い (passkey vs ID/PW) のため別 API。これは妥当 (認証方式が違うのに同 API は不可能)。

## 実装

### ファイル

- `src/moneyforward_pk/auth/__init__.py` 新規 (パッケージ初期化、SessionManager export)
- `src/moneyforward_pk/auth/session_manager.py` 新規 (SessionManager クラス)
- `src/moneyforward_pk/spiders/base/moneyforward_base.py` 改修
- `tests/test_session_manager_unit.py` 新規 (9 ケース)

### SessionManager API

```python
class SessionManager:
    def __init__(self, state_dir: Path, site: str, login_user: str): ...
    def has_saved_session(self) -> bool: ...
    def get_storage_state(self) -> str | None: ...
    async def save_from_context(self, context) -> None: ...
    def invalidate_session(self) -> None: ...
```

state ファイル: `runtime/state/{site}_{user_hash[:12]}.json` (email は SHA-256 で hash 化、ファイル名から漏らさない)

### Spider 統合

1. `from_crawler` で SessionManager 構築 (login_user 必須、無い時はスキップ)
2. `_build_login_request`: 既存 state あれば `playwright_context_kwargs={"storage_state": <path>}` を meta 注入
3. `_parse_after_login`: `_is_logged_in_page(page)` (logout link 存在チェック) で既ログイン判定
   - 既ログイン → login_flow スキップ + `{name}/login/skipped` stats
   - 未ログイン → login_flow 実行
4. ログイン成功後 `session_manager.save_from_context(context)` で state 保存
5. ログイン失敗時 `session_manager.invalidate_session()` で state 削除

### login_flow セレクタ修正

当初プラン: suffix match + fallback。

実装: **セレクタクリック自体を廃止**し
`page.goto(variant.login_url)` で直接ログインフォームへ遷移。
top page header の DOM が variant ごとに異なり JS-rendered の場合もあるため
クリック方式は廃止が最良と判断。

派生変更:

- `VariantConfig.login_url` プロパティ追加 (registry.py)
  - `is_partner_portal=True` → `{base}/users/sign_in`
  - `is_partner_portal=False` → `{base}/sign_in`
- 1-page form (xmf_*) / 2-page form (mf) 自動判定:
  email 入力後 password locator を probe → count > 0 で 1-page 判定。

### `_parse_after_login` 戻り値の変更 (12 ヶ月取得バグ修正)

当初実装: async generator (`async def ... yield`).
Scrapy エンジンが lazy に pull するため、12 ヶ月分の Request を yield しても
1 件しかキューイングされず、SITE_PAST_MONTH=12 で 1 ヶ月しか取得できない事象が発生。

修正: **list を返す coroutine** に変更。
`async for x in self._iter_after_login(post_login): results.append(x)` で
全件収集してから `return results`。Scrapy が確実に 12 件 enqueue。

```python
async def _parse_after_login(self, response: Response):
    page = response.meta.get("playwright_page")
    if page is None:
        return []
    # ... login flow ...
    results: list = []
    async for item_or_request in self._iter_after_login(post_login):
        results.append(item_or_request)
    return results
```

## 検証

- ruff clean
- pytest 257 件 全 pass (既存 239 + SessionManager 9 新規 + login_flow_selectors 8 新規 + 既存テスト改修)
- 不要な pytest-asyncio 依存を回避 (既存 `_drive` パターン踏襲、`asyncio.new_event_loop().run_until_complete`)
- E2E 動作検証は実環境必要 (user 環境で `crawl-asset` 等)

## 残作業

- [完了] `runtime/state/` を `.gitignore` に追加 (`/runtime/`, `src/runtime/`, `config/accounts.yaml`, `config/*.local.yaml`, `config/secrets/`)
- [完了] middleware の session expiry 時に `session_manager.invalidate_session()` 連携 (middlewares/playwright_session.py L57-59) + 再試行で stale `playwright_context_kwargs` を drop (L70)
- [完了] `_parse_after_login` を list-return coroutine に変更 (12 ヶ月取得バグ修正)
- [完了] `VariantConfig.login_url` プロパティ追加 + login_flow を直接 goto 方式に置換
- [完了] 1-page / 2-page form 自動判定追加
- [ ] PR description / README 更新 (session persistence 機構の説明追加)
- [ ] commit / push / PR 作成
- [完了] E2E 検証 (2 回目起動): `login/skipped: 1` + `Reusing saved session` 確認 (2026-04-28)
- [完了] state 保存確認: `runtime/state/xmf_ssnb_<hash>.json` 生成 (2026-04-28)

## #43 範囲外として切り出した課題

- **#44** `MfTransactionSpider.after_login` が `past_months` 件 yield せず 1 件のみ取得
  - 元症状「12 ヶ月のうち 1 ヶ月しか取れない」「2 ページ問題」の真因
  - `_parse_after_login` の list-return 化 (本 PR で実装) では解消せず
  - yield 元 (`after_login` / `past_months` 解決) 側の問題で、session 永続化とは独立
  - 本 PR では touchせず、#44 で個別調査・修正する

## Issue #40 との関係

- 本 PR (#43) は master ベース、Issue #40 (orchestrator) を含まない
- merge 順序: #43 → #40 (rebase 必要、orchestrator 側で session_manager を使う形に追従)
- どちらが先に merge しても他方は rebase で取り込み可能
