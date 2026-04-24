#!/usr/bin/env bash
# Usage: job_runner.sh <transaction|asset|account>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

PY="${PY:-$ROOT/.venv-win/Scripts/python.exe}"
if [[ ! -x "$PY" ]]; then
    PY="python"
fi

cmd="${1:-transaction}"
case "$cmd" in
    transaction|trans)  spider="mf_transaction"        ;;
    asset|allocation)   spider="mf_asset_allocation"   ;;
    account|accounts)   spider="mf_account"            ;;
    *)
        echo "Usage: $0 <transaction|asset|account>" >&2
        exit 2
        ;;
esac

cd src
exec "$PY" -m scrapy crawl "$spider"
