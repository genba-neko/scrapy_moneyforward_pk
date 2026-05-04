# 分別管理資産・借入控除ロジックの移植 (旧PJ → 本PJ)

## 背景

旧 `scrapy_moneyforward` PJ には `MoneyforwardAssetAllocation.adjust_segregated_asset(date_now)`
が存在し、以下を担っていた:

1. **分別管理資産** — MFが直接捕捉できない資産 (税金仮払い・ゆうちょ・JA銀行 等) を
   `asset_allocation_separate_amount` に加算し、レポート参考値として表示。
2. **借入控除** — 野村信託銀行 証券担保ローン短期 等の借入を、`total` および
   `待機資金` から減算 (実際の純資産を表示する)。

本PJの [src/moneyforward/reports/asset_allocation.py:119](../src/moneyforward/reports/asset_allocation.py#L119)
は `"separate": 0` ハードコードのままで、両ロジックが完全欠落している。
旧PJ実体: `C:\Users\g\OneDrive\devel\genba-neko@github\scrapy_moneyforward\src\moneyforward\tables\asset_allocation.py:101-220`

## ゴール

- `adjust_segregated_asset` 相当のロジックを純関数として復活
- 旧PJでハードコードだった `period_dict` / `period_dict_debt` を **外部YAML定義ファイル** に切り出し、
  期間データ追加・編集をコード変更なしで可能にする
- `asset_allocation` レポートCLI に統合、設定ファイル無しでも動作 (後方互換: 既存の `separate=0` 動作を維持)

## 設計

### 1. 定義ファイル形式: YAML

既存 `config/accounts.yaml` と統一。`config/segregated_asset.yaml` を新設。

```yaml
# 分別管理資産 (MFが捕捉できない資産を加算表示。total / クラス別金額は変えない)
segregated:
  - period: ["2022-12-22", "unlimited"]
    asset_class: "待機資金"
    amount: -300000
    note: "税金仮払い分"
  - period: ["2023-01-16", "unlimited"]
    asset_class: "待機資金"
    amount: 6141147
    note: "ゆうちょ分"
  - period: ["2023-03-07", "2025-12-10"]
    asset_class: "株式（長期）"
    amount: 2512000
    note: "日本電信電話"
  # ... 旧PJ全16件移植

# 借入 (total / 該当 asset_class から減算)
debt:
  - period: ["2022-09-26", "2022-10-04"]
    asset_class: "待機資金"
    amount: 2000000
    note: "野村信託銀行証券担保ローン短期"
  # ... 旧PJ全21件移植
```

### 2. 新規モジュール: `src/moneyforward/reports/segregated_asset.py`

純関数3つで構成:

- `load_segregated_config(path: Path) -> dict`
  - YAML 読込み + 簡易バリデーション (period長さ2、日付フォーマット、amount int、asset_class が ASSET_CLASSES に含まれる)
  - 不在時は `{"segregated": [], "debt": []}` を返す (no-op)
- `compute_adjustments(config: dict, target: date) -> dict`
  - 期間判定 (unlimited対応): `start <= target <= end` (end=unlimited なら end=∞)
  - 旧PJ `get_amount_for_period` 相当
  - 戻り値: `{"segregated": {asset_class: int}, "debt": {asset_class: int}}`
  - 開始日 unlimited は `ValueError` (旧PJ仕様継承)
- `apply_adjustments(aggregated: dict, adjustments: dict) -> dict`
  - 既存 `aggregate_asset_allocation` 戻り値を補正
  - segregated: `aggregated["separate"]` に合算
  - debt: `aggregated["total"]` および `aggregated["classes"][asset_class]` から減算
  - 戻り値は新dict (副作用なし)

### 3. CLI 統合: `src/moneyforward/reports/cli.py`

`asset_allocation` サブコマンドに `--segregated-config <path>` 追加:
- 既定: `config/segregated_asset.yaml`
- ファイル不在: 警告ログのみで no-op (現状動作互換)
- `--no-segregated-config` フラグで明示OFF (テスト/比較用)

`_cmd_asset_allocation`:

```python
aggregated = aa_mod.aggregate_asset_allocation(daily)
config_path = args.segregated_config
if config_path and config_path.exists():
    cfg = load_segregated_config(config_path)
    adj = compute_adjustments(cfg, date(args.year, args.month, args.day))
    aggregated = apply_adjustments(aggregated, adj)
return aa_mod.report_message(aggregated, args.year, args.month, args.day)
```

### 4. テンプレート/ gitignore

- `config/segregated_asset.example.yaml` — 旧PJ全エントリそのまま (37件) コミット対象
- `config/segregated_asset.yaml` — `.gitignore` 入り (個人金融データ)
- README に「設定方法」節追記: example をコピーして編集する流れ

### 5. テスト: `tests/test_segregated_asset_unit.py`

最低8ケース:
1. `load_segregated_config` 正常 YAML
2. `load_segregated_config` ファイル不在 → 空辞書
3. `load_segregated_config` 不正 schema → `ValueError`
4. `compute_adjustments` 期間内 (unlimited 終了)
5. `compute_adjustments` 期間外
6. `compute_adjustments` 開始 unlimited → ValueError
7. `compute_adjustments` 複数エントリ同 asset_class 合算
8. `apply_adjustments` segregated/debt 同時適用 → total・classes・separate 全て更新確認
9. CLI スモーク: `--segregated-config` 指定で報告メッセージに分別管理金額が反映

## ファイル一覧

新規:
- `config/segregated_asset.example.yaml` (旧PJ全データ)
- `src/moneyforward/reports/segregated_asset.py`
- `tests/test_segregated_asset_unit.py`
- `tests/fixtures/segregated_asset_sample.yaml` (テスト用ミニ定義)

修正:
- `src/moneyforward/reports/cli.py` (`--segregated-config` 追加、`_cmd_asset_allocation` 連結)
- `.gitignore` (`config/segregated_asset.yaml` 追記)
- `README.md` (設定方法節追記)
- `plan/20260505_0243_segregated_asset_migration.md` (本ファイル)

## 受け入れ基準

- [ ] 旧PJ `period_dict` / `period_dict_debt` 全37件が `config/segregated_asset.example.yaml` に再現
- [ ] `python -m moneyforward.reports asset_allocation -y 2024 -m 2 -d 18` (旧PJと同条件) 実行で
      `分別管理資産=...円` 表示が旧PJ出力と一致 (待機資金=1369295 加算想定)
- [ ] 設定ファイル不在時は現状の `分別管理資産=0円` 表示で従前互換
- [ ] `pytest tests/test_segregated_asset_unit.py` 全パス
- [ ] `tests/test_reports_cli_unit.py` の `asset_allocation` 既存テストが引き続き通る

## ブランチ名候補

`feature/<issue#>_segregated_asset_migration`

## ステータス

- [ ] issue 作成
- [ ] ブランチ作成
- [ ] 設定ファイル雛形コミット
- [ ] segregated_asset.py 実装
- [ ] CLI 統合
- [ ] テスト
- [ ] README 更新
- [ ] PR 作成
- [ ] master マージ

## 関連資料

- 旧PJ実装: `C:\Users\g\OneDrive\devel\genba-neko@github\scrapy_moneyforward\src\moneyforward\tables\asset_allocation.py:101-220`
- 旧PJ呼出: `C:\Users\g\OneDrive\devel\genba-neko@github\scrapy_moneyforward\src\get_asset_allocation_report.py:44-46`
- 本PJ既存: [src/moneyforward/reports/asset_allocation.py](../src/moneyforward/reports/asset_allocation.py)
