# Issue #48: Python CI が workbench submodule 不在で永続 RED の修正

作成: 2026-05-02 15:03
ブランチ: `fix/48_ci_workbench_pat` (起点 master)
関連 issue: #48

## 背景

`.github/workflows/python-ci.yml` の lint / test 両ジョブが、 checkout 時に
`submodules: false` を指定しているため workbench submodule が展開されない。
にもかかわらず install ステップで以下を実行している:

```yaml
- run: pip install -r workbench/python/requirements.txt
- run: pip install -r .workbench/python/requirements.txt
```

→ `No such file or directory: 'workbench/python/requirements.txt'` で fatal。
master の Python CI は 2026-04-25 以降 永続 RED 状態。

## 履歴

`plan/20260426_1000_iteration_log.md` の review_carryovers に既知記録あり:

> pip install -r workbench/python/requirements.txt が submodules:false 状態で
> fatal、 master CI 永続 RED。 fix: workbench 依存 2 行削除 or if-files-exist
> ガード。 deferred_reason: 本イテレーション T1 lock file 範囲外、 admin merge
> で実害回避済。

PR #47 (feat/40_variant_orchestrator) の merge 検討時に再度顕在化したため、
本 issue で恒久対応する。

## 対応方針

ユーザ確認: `PAT_TOKEN` という名前で submodule 取得用 PAT が
リポジトリ secrets に登録済。 これを利用して checkout 時に submodule を
有効化する。

```yaml
- uses: actions/checkout@v4
  with:
    submodules: true
    token: ${{ secrets.PAT_TOKEN }}
```

lint / test 両ジョブの 2 箇所を更新。

## 影響範囲

- `.github/workflows/python-ci.yml` 1 ファイル / 2 箇所
- 他 workflow (`scrapy-nightly.yml`) は本 PR 範囲外 (別途必要なら別 issue)

## 検証

- push 後の CI run で lint / test 両ジョブが緑になることを確認
- 既存の workbench/python/requirements.txt と
  `.workbench/python/requirements.txt` 双方が install 成功すること
- ruff / pyright / pytest が通ること

## task

- [x] issue #48 起票
- [x] ブランチ `fix/48_ci_workbench_pat` 作成
- [ ] `.github/workflows/python-ci.yml` の 2 checkout step に
      `submodules: true` + `token: ${{ secrets.PAT_TOKEN }}` 追加
- [ ] commit + push
- [ ] PR 作成 → CI 緑確認 → merge
