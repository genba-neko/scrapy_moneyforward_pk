# パッケージ rename: moneyforward_pk → moneyforward

作成: 2026-05-04  
Issue: #55 (予定)

## 背景

旧PJ (`../scrapy_moneyforward`) 停止済み。`_pk` サフィックスは競合回避目的で付与されていたが不要になった。  
`moneyforward_pk` → `moneyforward` に全面 rename する。

---

## 変更スコープ

### ディレクトリ

| 変更前 | 変更後 |
|--------|--------|
| `src/moneyforward_pk/` | `src/moneyforward/` |

### 設定ファイル

| ファイル | 変更前 | 変更後 |
|----------|--------|--------|
| `src/scrapy.cfg` | `default = moneyforward_pk.settings` | `default = moneyforward.settings` |
| `src/scrapy.cfg` | `project = moneyforward_pk` | `project = moneyforward` |
| `src/moneyforward/settings.py` | `BOT_NAME = "moneyforward_pk"` | `BOT_NAME = "moneyforward"` |
| `src/moneyforward/settings.py` | `SPIDER_MODULES = ["moneyforward_pk.spiders"]` | `["moneyforward.spiders"]` |
| `src/moneyforward/settings.py` | `NEWSPIDER_MODULE = "moneyforward_pk.spiders"` | `"moneyforward.spiders"` |
| `src/moneyforward/settings.py` | DOWNLOADER_MIDDLEWARES キー (`moneyforward_pk.*`) | `moneyforward.*` |
| `src/moneyforward/settings.py` | ITEM_PIPELINES キー | `moneyforward.*` |
| `src/moneyforward/settings.py` | EXTENSIONS キー | `moneyforward.*` |
| `src/moneyforward/settings.py` | log デフォルト `moneyforward_pk.log` | `moneyforward.log` |
| `.env.example` | `LOG_FILE_PATH=runtime/logs/moneyforward_pk.log` | `moneyforward.log` |
| `job_runner.sh` | `-m moneyforward_pk.crawl_runner` | `-m moneyforward.crawl_runner` |

### Python import (src/ 全体)

`from moneyforward_pk.` → `from moneyforward.`  
`import moneyforward_pk` → `import moneyforward`

### テスト (tests/ 29 ファイル)

同上。全 import を置換。

### ドキュメント

| ファイル | 対応 |
|----------|------|
| `CLAUDE.md` | `moneyforward_pk` → `moneyforward` (3 箇所) |
| `docs/migration_mapping.md` | 同上 |
| `README.md` | 同上 |
| `CONTRIBUTING.md` | 同上 |
| `plan/` 各 md | 同上 (任意) |

---

## 変更しないもの

| 項目 | 理由 |
|------|------|
| git リポジトリ名 `scrapy_moneyforward_pk` | GitHub remote 変更は別途判断 |
| 出力ファイル名 `moneyforward_{type}.json` | `_pk` なしのまま → rename 後も一致 |
| 環境変数プレフィックス `MONEYFORWARD_` | すでに `_PK` なし → そのまま |

---

## 実装手順

1. **既存ログファイル rename** (互換維持):
   ```powershell
   Get-ChildItem runtime/logs/moneyforward_pk.log* | ForEach-Object {
       Rename-Item $_ ($_.Name -replace 'moneyforward_pk', 'moneyforward')
   }
   ```
2. `src/moneyforward_pk/` ディレクトリを `src/moneyforward/` に rename
3. `src/moneyforward/` 配下の全 `.py` 内の `moneyforward_pk` を `moneyforward` に一括置換
4. `src/scrapy.cfg` 更新
5. `tests/` 全ファイルの import 置換
6. `job_runner.sh` 更新
7. `.env.example` 更新
8. `CLAUDE.md` / `README.md` / `CONTRIBUTING.md` / `docs/` 更新
9. lint + pyright + pytest 通過確認

---

## 注意点

- `moneyforward` は PyPI に同名パッケージが存在する可能性あり。ローカル専用用途なので問題なし。
- rename 後 `pyproject.toml` の `pythonpath = ["src"]` はそのまま有効 (パッケージ名変更だけなので)。
- 既存ログ (`moneyforward_pk.log*`) は手順 1 で rename し、ログ継続性を維持する。
