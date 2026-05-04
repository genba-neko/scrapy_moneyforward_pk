# chore: 不要アーティファクト 棚卸・削除

## 背景

プロジェクト成熟に伴い、過去の開発段階で作成したが現在は使われていない
ファイル・フォルダが蓄積している。git 上の tracked ファイルを中心に整理する。

## 棚卸結果

### git tracked（要対応）

| パス | 判定 | 理由 |
|---|---|---|
| `tools/secrets/bws_tool.py` | **要評価** | Bitwarden admin CLI。`src/moneyforward/secrets/` は runtime 用途で別物。ops 用として残すか判断が必要 |
| `docs/migration_mapping.md` | **削除候補** | legacy scrapy_moneyforward (Splash) → Playwright 移行が完了。参照用途終了 |
| `data/backup/` | **整理候補** | 空フォルダ、`.gitkeep` なし。git 上に存在意義なし |

### gitignore 済み（git 対象外・ローカル清掃のみ）

| パス | 内容 |
|---|---|
| `.venv-wsl/` | WSL Python venv。Windows 専用運用なら不要 |
| `data/fixutres_source/` | HTML fixtures ソース（手動キャプチャ）。テストに直接不使用 |
| `.work/olddata/` | 旧 CSV 結果。`.work/` は gitignore |

### 現状維持（対応不要）

| パス | 理由 |
|---|---|
| `requirements.txt` | `pyproject.toml` に `[project.dependencies]` なし → 依存定義の唯一ファイル |
| `.env.example` | 全キーが `settings.py` で現役参照確認済み |
| `job_runner.sh` / `.bat` | CLAUDE.md で互換維持対象と明記 |
| `workbench/` (submodule) | 現役 (pre-commit hooks 等) |
| `.workbench/` | workbench プロジェクト設定、現役 |
| `tools/secrets/__init__.py` | `bws_tool.py` の判断に依存 |

## 作業スコープ（git 対象）

### Step 1: `docs/migration_mapping.md` 削除

- 移行完了済み
- 参照用途終了
- `plan/` に移動してアーカイブ（削除でも可）

### Step 2: `data/backup/` 整理

- 空フォルダ → `.gitkeep` 追加か、フォルダごと `.gitignore` から除外して削除

### Step 3: `tools/secrets/bws_tool.py` 用途確認・判断

- 用途: Bitwarden Secrets の list / read / register / dump / delete 操作 CLI
- `src/moneyforward/secrets/` は runtime 読み込みのみで管理操作は行わない
- **判断**: 残す → `tools/secrets/README.md` 追加済み ✅

### Step 4: `.workbench/archive_rules` に inspect アーカイブルール追加

- `runtime/inspect/` に YYYYMMDD_HHMMSS_spider 形式でディレクトリ蓄積
- smbcnikko_pk 同様に DATED ルールで日次 zip アーカイブ → 元削除
- 追加内容: `DATED  runtime\inspect   data\archive_inspect  inspect   DELETE` ✅

### Step 5: キャッシュディレクトリ生成抑止 (smbcnikko_pk 踏襲)

smbcnikko_pk との設定統一。3 種のキャッシュを対象とする。

#### `__pycache__` 抑止

- `PYTHONDONTWRITEBYTECODE=1` を `job_runner.sh` の `exec` 直前に追加
  - `job_runner.bat` → `wsl_runner.bat` → `job_runner.sh` のチェーンなので1箇所で全カバー
- `.env.example` に `PYTHONDONTWRITEBYTECODE=1` を追記
  - コメント: `load_dotenv()` では効果なし、シェル起動前に設定が必要

#### `.pytest_cache` 抑止

- `pyproject.toml` `[tool.pytest.ini_options]` addopts に `-p no:cacheprovider` 追加
- smbcnikko_pk は `pytest.ini` で同設定済み

#### `.ruff_cache` 抑止

- `pyproject.toml` `[tool.ruff]` に `cache-dir = "~/.cache/ruff"` 追加
  - プロジェクトディレクトリ外（ユーザーホーム）へ移動
  - smbcnikko_pk には未対応 → こちら独自追加

### Step 6: `.env.example` 整理 — 設定キー有効性確認

全キーを実装照合した結果:

- **無効キー**: `MONEYFORWARD_LOGIN_MAX_RETRY` — `settings.py` 未定義のため `crawler.settings.getint()` が env 値を受け取れず常に default `2` を使用。
  - 修正: `settings.py` に `MONEYFORWARD_LOGIN_MAX_RETRY = int(os.environ.get(..., "2"))` 追加
- **未実装キー**: `SITE_LOGIN_ALT_USER` / `SITE_LOGIN_ALT_PASS` — src/ に実装なし。README.md の「アカウント切替」節を削除。
- その他全キー: 実装と一致 ✅

## 完了事項

- `tools/secrets/bws_tool.py` → 残す（`tools/secrets/README.md` 追加）✅
- `docs/migration_mapping.md` → `plan/20260425_2227_migration_mapping.md` にアーカイブ ✅
- `plan/USER_DIRECTIVES.md` → `plan/rules/USER_DIRECTIVES.md` に移動 ✅
- `data/backup/.gitkeep` 追加 ✅
- `data/fixutres_source/.gitkeep` 追加 ✅
- `.workbench/archive_rules` に inspect DATED ルール追加 ✅
- `runtime/{inspect,logs,output,state}/`, `data/{archive,archive_inspector}/` `.gitkeep` 整備 ✅
- `.gitignore` `!runtime/*/` 除外例外追加 ✅
- `ARCHITECTURE.md` 新規・`README.md`/`CONTRIBUTING.md`/`CLAUDE.md` 最新化 ✅
- `__pycache__`/`.pytest_cache`/`.ruff_cache` 生成抑止設定追加 ✅
- `settings.py`: `MONEYFORWARD_LOGIN_MAX_RETRY` 追加 (env → Scrapy 設定疎通修正) ✅
- `README.md`: 未実装の「アカウント切替 (SITE_LOGIN_ALT_USER)」節を削除 ✅

## 関連 issue

- issue #63（本プラン対応 issue）
