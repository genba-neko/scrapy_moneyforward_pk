# Architecture

## Module Map

```
src/moneyforward/
├── settings.py            # Scrapy settings, .env loading, Playwright wiring
├── items.py               # Transaction / Account / AssetAllocation items
├── pipelines.py           # JsonArrayOutputPipeline — streaming JSON-array writer
├── crawl_runner.py        # CLI: reads config/accounts.yaml, dispatches _runner_core
├── _runner_core.py        # Multi-site × multi-account loop, output file lifecycle
├── auth/
│   └── session_manager.py # Playwright storage_state persistence (login session cache)
├── extensions/
│   └── slack_notifier_extension.py  # spider_closed → Slack webhook
├── middlewares/
│   ├── playwright_session.py        # Session expiry detection + forced re-login
│   └── html_inspector.py            # Debug: saves response HTML to runtime/inspect/
├── reports/               # JSON output → Slack messages / CSV (balances, asset-allocation)
├── seccsv/                # Securities broker CSV → MoneyforwardTransactionItem
├── secrets/
│   ├── resolver.py        # SECRETS_BACKEND switch: env vs Bitwarden
│   ├── bws_provider.py    # Bitwarden Secrets Manager client
│   └── exceptions.py
├── spiders/
│   ├── base/moneyforward_base.py  # Login flow, credential resolution, force-relogin
│   ├── variants/registry.py       # VARIANTS dict: site-id → base URL + login selectors
│   ├── _parsers.py        # Pure HTML parsers (no Scrapy dependency; testable with fixtures)
│   ├── transaction.py
│   ├── asset_allocation.py
│   └── account.py
└── utils/
    ├── log_filter.py      # SensitiveDataFilter: redacts auth/cookie/password in logs
    ├── logging_config.py  # setup_common_logging, file handler wiring
    ├── paths.py           # resolve_output_dir (PROJECT_ROOT enforcement), sanitize_spider_name
    ├── playwright_utils.py # Page helpers, resource type / URL blocking
    ├── session_utils.py   # storage_state load/save helpers
    └── slack_notifier.py  # HTTP webhook sender (pure util; used by extension)
```

## Data Flow

```
config/accounts.yaml
        │
crawl_runner.py ──► _runner_core.py
                          │
                          ├── initialize_output_files()
                          │       └── truncate each *.json to "["
                          │
                          ├── for each site × account:
                          │       CrawlerProcess
                          │         ├── MoneyforwardBase.login_flow (Playwright)
                          │         │     └── resolver.py → env / BWS credentials
                          │         ├── Spider → _parsers.py → Item
                          │         └── JsonArrayOutputPipeline.process_item()
                          │               └── append JSON (indent=2) to runtime/output/*.json
                          │
                          └── finalize_output_files()
                                  └── append "\n]" to each *.json
```

## Spider Classes (3 fixed)

| Spider | Output Item |
|---|---|
| `transaction` | `MoneyforwardTransactionItem` |
| `account` | `MoneyforwardAccountItem` |
| `asset_allocation` | `MoneyforwardAssetAllocationItem` |

Site variant is `-a site=<id>`. Variants are registered in `spiders/variants/registry.py`.

## Secrets Resolution

Two backends selected by `SECRETS_BACKEND` env:

| Mode | Credentials source |
|---|---|
| `env` (default) | `.env` / shell env |
| `bitwarden` | Bitwarden Secrets Manager, keys prefixed `MONEYFORWARD_*` |

Credentials are never written to logs (`SensitiveDataFilter` redacts at root logger level).

## Output Files

`JsonArrayOutputPipeline` streams items into 3 aggregated JSON arrays:

```
runtime/output/
├── moneyforward_transaction.json
├── moneyforward_account.json
└── moneyforward_asset_allocation.json
```

Per-run lifecycle (crawl_runner):
1. `initialize_output_files()` — truncate each to `[` (1 byte)
2. `process_item()` — detect fresh file via `size == 1`, append items with `,\n` separator
3. `finalize_output_files()` — append `\n]`

Single `scrapy crawl` without crawl_runner appends to existing file (no initialization step).

## Runtime Directory Layout

```
runtime/
├── inspect/    # HtmlInspectorMiddleware output: YYYYMMDD_HHMMSS_{spider}/
├── logs/       # Log files (LOG_FILE_ENABLED=true)
├── output/     # Crawl JSON arrays (3 files)
└── state/      # Playwright storage_state (session persistence)
```

Archive rules (`.workbench/archive_rules`):
- `runtime/output/` → `data/archive/` BULK, source kept
- `runtime/inspect/` → `data/archive_inspector/` DATED by YYYYMMDD, source deleted

## Key Design Decisions

- **`_parsers.py` pure functions**: HTML → Item with no Scrapy dependency, testable with HTML fixtures only
- **`PLAYWRIGHT_CONTEXTS = {}`**: empty so first Request can inject `storage_state` via `playwright_context_kwargs`
- **`size == 1` heuristic**: `JsonArrayOutputPipeline.open_spider` detects fresh `[`-only file (1 byte) vs file with prior items
- **`paths.resolve_output_dir`**: enforces `OUTPUT_DIR ⊆ PROJECT_ROOT`; rejects `..` traversal and external symlinks
- **`SensitiveDataFilter`**: attached to root logger at startup, idempotent, redacts `auth=` / `token=` / `Cookie:` / `Authorization:` / `password=`
- **`PlaywrightSessionMiddleware`**: detects `/sign_in` redirect, sets `moneyforward_force_login=True`, retries; on second retry uses `SITE_LOGIN_ALT_USER` if configured

## Field Names (Upstream Compatibility)

Output field names match the DynamoDB key schema used by the predecessor project.
**Do not rename these fields** without coordinating with upstream consumers.

| Spider | PK field | SK field |
|---|---|---|
| `transaction` | `year_month` | `data_table_sortable_value` |
| `asset_allocation` | `year_month_day` | `asset_item_key` |
| `account` | `year_month_day` | `account_item_key` |

## Tools

```
tools/
├── passkey/               # Passkey / WebAuthn helper scripts
└── secrets/
    ├── bws_tool.py        # Bitwarden Secrets admin CLI (list/read/register/dump/delete)
    └── README.md
```

`tools/secrets/bws_tool.py` is an admin-only CLI for managing Bitwarden secrets.
It is separate from `src/moneyforward/secrets/` which handles runtime resolution only.
