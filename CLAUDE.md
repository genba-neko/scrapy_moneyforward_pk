# CLAUDE.md

## プロジェクトルール

### プラン作成

- 保存先: `plan/YYYYMMDD_HHMM_概要.md`（時刻: `date +%Y%m%d_%H%M`）
- 開始時: 【プラン作成モード開始】を応答

### issue 登録

- ユーザー価値・機能単位で分割。細かい準備/docs 追従は本体 issue に吸収
- issue 本文に「関連資料」セクションで `plan/` ファイルへリンク
- ラベル: `feat` / `fix` / `refactor` / `test` / `chore` / `docs`

### 実装フロー

1. ブランチ名提案 → 決定: 人間
2. 設計・実装・レビュー・テスト
3. **プラン完了マーク**: コミット前に `plan/` 該当 issue へ `[完了 PR#XX YYYY-MM-DD]` 追記
4. コミット・マージ: 人間判断

- プラン議論中は実装着手しない（コード diff・新規ファイル生成禁止）
- 実装フェーズはユーザー明示指示後のみ開始
- `commit` / `push` / `merge` / `rebase` / PR 作成はユーザー明示指示まで実行しない
- 実装完了後: push → PR → master マージ → `git pull`
- **プランと実態が乖離したら即時 `plan/` 更新（確認不要）**
- PR 未作成のまま merge 禁止
- squash merge 禁止（merge commit を使う）
- **他エージェントへの依頼は人間の明示指示時のみ**

### ブランチ命名

`feature/[issue番号]_[概要]` / `fix/[issue番号]_[概要]`

### ブランチ運用 (重要)

- **master/main 直 commit 禁止**。コミット前に必ず `git branch --show-current` で確認
- `gh pr merge --delete-branch` 後、HEAD は自動的に master に戻る → 次の作業前に必ず新ブランチ切る
- 過去事例: PR #4 マージ後に master 直 commit 発生 (PR #33 で巻き戻し済)

### コミット規則

Conventional Commits: `feat:` / `fix:` / `chore:` など。
実装コミットには対応する `plan/*.md` も `git add` する。

### .env 編集時の半角チェック

- 半角英数字のみ。日本語 IME を切ってから編集
- 確認: `grep -nE "[Ａ-Ｚａ-ｚ０-９]" .env` で全角混入検出

### 破壊的操作の鉄則

削除・上書き・切り捨てを含む設計はコード前に人間へ危険性を説明し、安全側を提案。

1. **事前説明**: 消失リスクに気づいたらコード前に伝える
2. **安全側に倒す**: 削除より移動・アーカイブ。上書き前にバックアップ
3. **2ステップ順序保証**: 保存成功しない限り削除しない設計
