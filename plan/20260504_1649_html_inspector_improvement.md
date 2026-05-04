# html_inspector smbcnikko_pk 相当強化

作成: 2026-05-04 16:49  
Issue: #57  
Branch: `feature/57_html_inspector_improvement`

---

## 背景・議論サマリ

現状の `HtmlInspectorMiddleware` はすべてのダンプを `runtime/inspect/` 直下にフラット出力しており、複数実行の混在・フロー追跡が困難。

smbcnikko_pk の inspector 実装と比較し、以下を決定した。

### smbcnikko_pk との差分分析

| 機能 | smbcnikko_pk | moneyforward_pk (現状) | 方針 |
|------|-------------|----------------------|------|
| 実行単位サブディレクトリ | あり | なし | 移植 |
| flow.log (JSONL) | あり | なし | 移植 |
| URL パターンフィルタリング | あり（SMBC固有パス用） | なし | **不要**（master switch で十分） |
| Playwright load 補足 | あり | なし | 移植 |
| spider_opened/closed シグナル | あり | なし | 移植 |
| URL → フォルダ構造 | SMBC固有URL除去ロジックあり | なし | MF独自実装（パス直マッピング） |
| エラーページ検出 | CSS + NOLコード正規表現（SMBC固有） | なし | MF独自実装（HTTP status >= 400） |
| charset 修正 | Shift_JIS → utf-8 | 不要 | 不要（MFページはUTF-8） |

### URL マッピング方針

SMBC は `/OdrMng/{onetime_code}/sinyo/genbiki` のようなワンタイムコードを除去する必要があるが、MF のURL構造にはそのような要素がない。URL path をそのままサブディレクトリにマッピングするだけで十分。

例: `https://moneyforward.com/accounts/show` → `accounts/show.html`

### エラー検出方針

SMBC 固有の `span.txt_b02` CSS / `NOL\d{5}E` 正規表現は不要。  
`response.status >= 400` をエラーとし `_error.html` suffix を付与。

---

## 出力構造（変更後）

```
runtime/inspect/
└── {YYYYMMDD_HHMMSS}_{spider}/
    ├── flow.log                    ← 遷移シーケンス（JSONL）
    ├── accounts/
    │   ├── 001_show.html
    │   └── 002_edit.html
    └── transactions/
        └── 003_index.html
```

**flow.log エントリ例:**
```json
{"seq": 1, "time": "13:20:01", "callback": "parse_accounts", "path": "accounts/show", "file": "accounts/001_show.html", "error": false, "query": ""}
```

---

## 設定キー

| キー | デフォルト | 説明 |
|------|-----------|------|
| `MONEYFORWARD_HTML_INSPECTOR` | `false` | マスタースイッチ |
| `MONEYFORWARD_HTML_INSPECTOR_DIR` | `""` | 出力ディレクトリ上書き |

---

## 変更スコープ

- `src/moneyforward/middlewares/html_inspector.py` — 全面書き換え
- `tests/test_html_inspector_middleware_unit.py` — テスト更新

---

## 実装手順

1. `html_inspector.py` 書き換え
   - `from_crawler`: `run_dir` は `spider_opened` で確定
   - `spider_opened`: `run_dir = base / f"{ts}_{spider.name}"`、flow.log open
   - `spider_closed`: flow.log close
   - `process_response`: `_save` → Playwright listener attach
   - `_save`: URL path → サブディレクトリ変換、HTTP status エラー判定、flow.log 追記
   - `_attach_playwright_listener`: `page.on("load")` 登録
2. テスト更新
3. lint / pyright / pytest 通過確認
