# plan: #74 scrapy INFO ログ抑制

## ステータス

- [x] `scrapy` を noisy loggers に追加

## 背景

issue #74 (訂正済み)。

- ① Bitwarden 対応: PR#73 で実装済み。AXIOM_DATASET は設定値のため BWS 対象外
- ② scrapy INFO ログ抑制: 未対応 ← **本 plan の対象**

## 変更内容

### `src/moneyforward/utils/logging_config.py` line 113

```python
# before
for noisy in ("urllib3", "asyncio", "playwright"):
# after
for noisy in ("urllib3", "asyncio", "playwright", "scrapy"):
```

## 関連

- issue #74
- PR#73 (AXIOM Bitwarden 対応)
