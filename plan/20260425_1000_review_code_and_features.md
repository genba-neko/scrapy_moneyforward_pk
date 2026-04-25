# コードレビュー & 機能移植確認

実施日: 2026-04-25
モデル: Claude Sonnet 4.6 (コードレビュー: Opus 4.7)

## 目的

v1 ビルド完了後の品質確認。
1. コードレビュー (バグ・設計問題の洗い出し)
2. 元プロジェクト (`scrapy_moneyforward`) との機能移植率確認

---

## コードレビュー結果

### Critical (本番影響)

**C1. 再ログイン未配線**
- `middlewares/playwright_session.py` が `meta["moneyforward_force_login"] = True` をセットするが、`moneyforward_base.py` 側にフラグ処理なし
- セッション切れ1回で job が空走する致命傷
- 修正案: ミドルウェアで callback を差し替える or base spider に force_login 分岐を追加

**C2. `request.copy()` で closed page が残存**
- `playwright_session.py:54` のコピー後に `meta.pop("playwright_page", None)` が必要

### Major (9件)

| # | ファイル | 問題 |
|---|---|---|
| M1 | `playwright_utils.py:15` | `stylesheet` block → SPA 動的コンテンツが壊れる可能性 |
| M2 | `moneyforward_base.py:139` | `managed_page` と `errback_playwright` で page が二重 close |
| M3 | `moneyforward_base.py:142` | Playwright タイムアウト例外にログイン URL が含まれる可能性 |
| M4 | `_parsers.py:31` | `.transaction_list tr` セレクタが実 HTML fixture と乖離リスク |
| M5 | `_parsers.py:40` | `is_active` が行でなく子孫を探す — 誤検出 |
| M6 | `_parsers.py:154` | `parent::node()` 2段が実 HTML 構造と不一致リスク |
| M7 | `account.py:71` | C1 未修正状態で polling 中 session 切れ → 無限 retry |
| M8 | `settings.py:48` | `RETRY_HTTP_CODES` に 400 含む (Bad Request はリトライ不要) |
| M9 | `pipelines.py:62` | flush 失敗でバッチ消失 + `time.sleep` が reactor ブロック |

### Minor (14件)

- `setup_common_logging()` が import 副作用 → `from_crawler` 内へ移動
- `SlackNotifier` どこからも呼ばれない
- `XMoneyforwardLoginMixin` 未使用でカバレッジ歪み
- `parse_asset_allocation` が全テーブルの全 tr を取得 (1番目のみに限定すべき)
- `_DATE_SORT_RE` の年桁が無制限
- `SITE_LOGIN_ALT_USER` 読み込みのみで利用箇所なし
- `conftest.py` の env 注入が `setdefault` → CI 汚染リスク
- その他 7 件 (RULES5 採点ファイル参照)

---

## 機能移植率確認

元プロジェクト: `scrapy_moneyforward` (Scrapy + Splash + Lua)

### 完全移植 ✓

| 機能 | 状態 |
|---|---|
| Item フィールド (3クラス全フィールド) | 完全一致 |
| DynamoDB PK/SK 設計 | 完全一致 |
| mf_transaction (月数・分岐・日付) | 同等 |
| mf_asset_allocation | 同等 |
| mf_account (polling・sha256 key) | 同等 |
| ログイン (mfid_user系) | Lua→Playwright 全ステップ再現 |

### 未移植・機能後退

| 機能 | 重要度 | 備考 |
|---|---|---|
| DynamoDB テーブル切替ロジック (job_runner) | **高** | 本番データ破壊リスク |
| xmf_* パートナーポータル 24サブクラス | **高** | 元実運用の主スクレイプ対象 |
| spider_closed Slack 統計通知 | 中 | SlackNotifier は作成済みだが未配線 |
| GitHub Actions 定期実行 (毎週日曜) | **高** | CI は lint のみ |
| get_*.py レポート/ブログ/CSV 生成 8本 | **高** | 完全未移植 |
| tables/ 補正ロジック (period_dict 等) | **高** | 資産補正値が消失 |
| Makefile report/blog/today/csv ターゲット | 中 | 未移植 |
| ENV `DYNAMODB_TRANSACTION` 等3種 | **高** | job_runner 未移植に起因 |

### v1 スコープ外 (設計上の意図)

- 2FA 対応 (元プロジェクトも未対応)
- 状態機械 / パスキー / デーモン (smbcnikko_pk 固有)

---

## 良い点

- `managed_page` でページリーク防止
- `_parsers.py` 純関数分離 → unit test 容易
- `DynamoDbPipeline.from_crawler` で設定ミス即時検出
- `is_session_expired` の URL + title 二重判定
- DynamoDB `batch_writer` で 25-item 自動分割
- `Twisted<25` pin で asyncio reactor 互換担保
- `PLAYWRIGHT_CONTEXTS={}` の意図をテストで担保
