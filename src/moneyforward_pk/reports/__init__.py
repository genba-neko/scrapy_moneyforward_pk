"""集計レポート群 (元 PJ の get_*_report 群を JSONL ベースで再実装).

JSONL 出力 (``runtime/output/*.jsonl``) を入力として、元 PJ の
``get_balances_report`` / ``get_asset_allocation_report`` /
``get_balances_csv`` 相当のレポートを生成する.

DynamoDB を介さず純粋に JSONL ファイルから集計するため、テスト容易性が高い.
"""
