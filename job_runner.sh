#!/usr/bin/env bash
# Usage: job_runner.sh [transaction|asset|account|all]
#
# Backwards-compatible wrapper: dispatches to crawl_runner with the matching
# --type filter. Bare "all" (or empty) runs every configured site x account
# x spider type.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

if [[ -z "${PY:-}" ]]; then
    if [[ -x "$ROOT/.venv-wsl/bin/python" ]]; then
        PY="$ROOT/.venv-wsl/bin/python"
    elif [[ -x "$ROOT/.venv/bin/python" ]]; then
        PY="$ROOT/.venv/bin/python"
    elif grep -qi microsoft /proc/version 2>/dev/null; then
        if command -v python3 >/dev/null 2>&1; then
            PY="python3"
        else
            PY="python"
        fi
    elif [[ -x "$ROOT/.venv-win/Scripts/python.exe" ]]; then
        PY="$ROOT/.venv-win/Scripts/python.exe"
    elif command -v python3 >/dev/null 2>&1; then
        PY="python3"
    else
        PY="python"
    fi
fi

cmd="${1:-all}"
if [[ "$cmd" == --* ]]; then
    cmd="all"
else
    shift || true
fi
case "$cmd" in
    transaction|trans)  spider_type="transaction"      ;;
    asset|allocation)   spider_type="asset_allocation" ;;
    account|accounts)   spider_type="account"          ;;
    all|"")             spider_type=""                 ;;
    *)
        echo "Usage: $0 [transaction|asset|account|all]" >&2
        exit 2
        ;;
esac

cd src
if [[ -n "$spider_type" ]]; then
    exec "$PY" -m moneyforward_pk.crawl_runner --type "$spider_type" "$@"
else
    exec "$PY" -m moneyforward_pk.crawl_runner "$@"
fi
