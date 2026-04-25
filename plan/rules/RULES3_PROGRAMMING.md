# RULES3_PROGRAMMING.md — 実装

## 目的

RULES2 で作成したプランに従って実装し、各タスク完了後にテストで検証する。

## 事前読取 (必須)

1. `plan/CURRENT_ITERATION.md` を読む → `plan_file` フィールドのパスを取得
2. そのプランファイルを読む (「最新の PLAN_*.md を探す」は禁止)
3. 元プロジェクト参照が必要なタスクのみ、該当ファイルを読む

## 実施順序

プランの「実施順序 (依存グラフ)」に厳密に従う。
依存タスクが完了していないものに着手禁止。

## 1タスクの実施手順

```
1. タスクの「問題」「実装方針」「変更ロック」を読む
2. 変更ロックに列挙されたファイルだけ Read する
3. ★変更ロック外のファイルへの Edit/Write は禁止★
   (ロック外を変えたい場合 → 新規タスクとしてプランに追記してから実施)
4. 実装 (Edit / Write)
5. pytest tests/ -v --tb=short を実行 → 全 pass 確認
6. ruff check src/ tests/ を実行 → clean 確認
7. プランの完了判定チェックボックスを [x] に更新
8. 次のタスクへ
```

## コーディング規約

### スタイル (PEP 8 準拠)

- インデント: スペース4つ
- 行長: 最大99文字 (`pyproject.toml` の `line-length` に従う)
- 空行: トップレベル関数/クラスの間は2行、メソッド間は1行
- import 順: 標準ライブラリ → サードパーティ → ローカル (ruff `I` ルールで自動整列)
- 型ヒント: 新規関数・メソッドには必ず付ける

### コメント規則

**インラインコメント**: WHY が非自明な場合のみ1行。WHAT の説明は書かない。

```python
# Good: なぜこうするかが非自明
page.wait_for_timeout(3000)  # MF の画面遷移アニメーションが完了するまでの実測値

# Bad: コードを読めばわかる
items = []  # 空リストを作成
```

**書いてはいけないコメント**:
- 「何をしているか」の説明
- コミットメッセージに書くべきことの説明 (`# Issue #123 の修正` 等)
- 削除したコードの残骸 (`# old: xxx`)

### Docstring 規則 (Numpy 形式)

`pyproject.toml` で `D` (pydocstyle) ルールが `convention = "numpy"` で有効。
既存コードの missing docstring (D1xx) は後続イテレーションで順次解消する。
**新規追加する公開クラス・公開メソッド・公開関数には必ず Numpy 形式 docstring を書く** (D1xx を意図的に ignore しているが、新規コードで省略するのは禁止)。
プライベート (`_` prefix) は任意。テスト関数は不要。

```python
def parse_transactions(response: HtmlResponse, login_user: str) -> list[dict]:
    """取引明細ページから取引 Item を抽出する。

    Parameters
    ----------
    response : HtmlResponse
        /cf ページの Scrapy レスポンス。
    login_user : str
        ログインユーザー識別子。asset_item_key の生成に使用。

    Returns
    -------
    list[dict]
        MoneyforwardTransactionItem の dict 表現のリスト。
        行に日付がない場合はスキップ。

    Notes
    -----
    手動/自動/振替の3種を ``_extract_account_cells`` で分岐する。
    振替行は amount_number が負値になる。
    """
```

**Docstring が必要な対象**:
- `class` 定義 (Spider・Pipeline・Middleware・Item)
- `def` / `async def` (公開メソッド・公開関数)
- モジュールレベル (ファイル先頭) — `"""モジュールの役割を1行で。"""` でよい

**Docstring に書かない内容**:
- 実装の詳細 (コードを読めばわかること)
- TODO / FIXME (GitHub Issue に書く)
- バージョン履歴

### コーディング制約

**禁止**:
- `time.sleep` を Twisted reactor 上で使う → `reactor.callLater` または async
- import 副作用 (モジュール読み込みで副作用が走る実装)
- 採点で加点された既存の良い実装を壊す変更
- 既存テストを削除・スキップして pytest を通す

**必須**:
- ruff S (security) / B (bugbear) ルールを維持
- `managed_page` context manager パターンを維持
- `_parsers.py` は純関数を維持 (副作用を入れない)
- 環境変数は `settings.py` 経由で取得
- 新規スパイダーは `MoneyforwardBase` を継承
- 新規テストの env 注入は `monkeypatch.setenv` を使う (`os.environ.setdefault` 禁止)

## DynamoDB 変更禁止キー

本番テーブルのキー設計を変えるな:
- transaction: PK=`year_month`, SK=`data_table_sortable_value`
- asset_allocation: PK=`year_month_day`, SK=`asset_item_key`
- account: PK=`year_month_day`, SK=`account_item_key`

## xmf_* スパイダー追加パターン

```python
class XmfFooSpider(XMoneyforwardLoginMixin, MoneyforwardBase):
    name = "xmf_foo"
    partner_url = "https://..."
    # login_flow は XMoneyforwardLoginMixin から継承
    # parse_* は MoneyforwardBase の具象実装を継承 or override
```

## タスク完了後のプランファイル更新

```markdown
**完了判定**:
- [x] pytest 全 pass ({N}/{N}) ← 実際の件数
- [x] ruff clean
- [x] {タスク固有の確認}
```

## コミット規則

### タイミング

タスク単位でコミット。以下が全て揃った段階でコミットする:
- pytest 全 pass
- ruff clean
- プランの完了判定チェックボックスが全て `[x]`

複数タスクをまとめてコミットしない。1タスク = 1コミットを原則とする。

### メッセージ形式 (Conventional Commits)

```
<type>(<scope>): <subject>

[任意の本文]
```

| type | 用途 |
|---|---|
| `feat` | 新機能・新スパイダー |
| `fix` | バグ修正 |
| `refactor` | 動作を変えない構造変更 |
| `test` | テスト追加・修正 |
| `docs` | ドキュメント・コメント・docstring |
| `chore` | 設定・依存・CI・job_runner |

scope は変更対象のモジュール名 (例: `middlewares`, `account`, `pipelines`)。
subject は 50 文字以内、英語、命令形。

コミットメッセージに Issue 番号を含める (`closes #N` で Issue 自動クローズ):

```bash
# 例
git commit -m "fix(middlewares): wire force_login flag to base spider reauth (closes #12)"
git commit -m "feat(account): restore per-spider DynamoDB table env switching (closes #12)"
git commit -m "test(parsers): add real HTML fixture for transaction selector (closes #13)"
git commit -m "chore(job_runner): restore DYNAMODB_TABLE_NAME switching logic (closes #13)"
```

同一 Issue に複数コミットが対応する場合、最後のコミットだけ `closes #N`、
それ以前は `refs #N` を使う (途中でクローズしない):

```bash
git commit -m "fix(middlewares): detect force_login flag (refs #12)"
git commit -m "fix(base): handle force_login in start() (closes #12)"
```

コミット後、CURRENT_ITERATION.md の `open_issues` から `closed_issues` へ移動:
```yaml
open_issues: [13]          # まだ残っている
closed_issues: [12]        # クローズ済み
```

### 本文 (任意・WHY が非自明な場合のみ)

```
fix(middlewares): wire force_login flag to base spider reauth

PlaywrightSessionMiddleware sets moneyforward_force_login=True on
session expiry, but MoneyforwardBase had no handler for this flag.
Without this fix, session expiry causes the job to silently return
empty results instead of re-authenticating.
```

### 禁止事項

- `--no-verify` (pre-commit hook スキップ) — hook が失敗したら原因を修正
- `--amend` でプッシュ済みコミットを書き換え
- テスト未確認のままコミット
- `git add .` の無差別ステージング — 変更ロックのファイルのみ `git add`

## 全タスク完了後

```bash
cd C:/Users/g/OneDrive/devel/genba-neko@github/scrapy_moneyforward_pk
.venv-win/Scripts/pytest.exe tests/ -v
.venv-win/Scripts/ruff.exe check src/ tests/
cd src && ../.venv-win/Scripts/scrapy.exe list
```

3コマンド全て正常終了を確認してから `plan/CURRENT_ITERATION.md` を更新し、RULES4_REVVUE.md へ進む。

## CURRENT_ITERATION.md の更新

全タスク完了・3コマンド確認後:
```
completed_tasks: [T1, T2, T3, ...]
programming_status: done
```

## エラーハンドリング (自動化モード)

ユーザーへの確認で止まらない。以下の方針で自動継続:

| 状況 | 処理 |
|---|---|
| タスク実装が技術的に不可能 | `skipped_tasks` に理由を記録してスキップ、次タスクへ |
| pytest FAIL が修正できない | 修正試行 2 回まで。2 回失敗したら `skipped_tasks` に記録してスキップ |
| 変更ロック外ファイルへの変更が必要と判明 | 新規タスクとしてプランに追記 → 次イテレーションで対処 |
| ruff 違反が解消できない | 違反を `skipped_tasks` に記録 → RULES4 で FAIL として扱う |

`skipped_tasks` の形式:
```yaml
skipped_tasks:
  - task: T2
    reason: "Playwright page.close() async 二重呼び出しの根本修正に実環境が必要"
    action: "次イテレーションのプランに引き継ぎ"
```

## 制約

- プラン外の改善を勝手に追加するな (スコープクリープ禁止)
- スキップしたタスクは必ず記録する (サイレント無視禁止)
