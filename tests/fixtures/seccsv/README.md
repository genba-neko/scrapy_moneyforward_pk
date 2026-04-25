# seccsv test fixtures

匿名化済みの証券会社ダウンロード CSV サンプル。
口座番号・銘柄・金額は架空のものに置換済み。

| ファイル | エンコーディング | 出典 (元 PJ ファイル名 prefix) |
|---|---|---|
| `specificaccountpl_anonymized.csv` | cp932 | 楽天証券 特定口座損益 |
| `DetailInquiry_anonymized.csv` | utf-8 | SBI 証券 入出金明細 |
| `New_file_anonymized.csv` | utf-8 | 野村證券 すべての取引履歴 |
| `SaveFile_anonymized.csv` | cp932 | SBI 証券 譲渡益税明細 |

各 CSV は `seccsv._parsers` のパース対象列構成・行マーカ (例: 「配当金」「税徴収額」) を再現するための最小サンプル。
