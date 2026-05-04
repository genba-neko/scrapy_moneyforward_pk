"""証券会社ダウンロード CSV を集計配当 CSV へ変換するパッケージ.

元 PJ ``seccsv_to_incomes.py`` (および ``tables/dividend_income.py``) を
JSONL リビルド向けに移植したもの. SBI 証券・楽天証券・野村証券の
ダウンロード CSV (cp932 / utf-8 混在) を読み、税引後配当を月次集計した
``dividend_income.csv`` を出力する.
"""
