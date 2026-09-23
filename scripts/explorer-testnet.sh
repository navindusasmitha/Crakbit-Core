#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${CRAKBIT_REFERENCE_TREE:-$ROOT/build/reference}"
SRC="$REF/explorer"
RUNTIME="${CRAKBIT_EXPLORER_DIR:-$ROOT/build/explorer-testnet}"
DATA="${CRAKBIT_TESTNET_DATA:-$ROOT/build/testnet-data}"
NODE_CONF="$DATA/crakbit.conf"
CONFIG="$RUNTIME/config.crakbit-testnet.json"
ACTION="${1:-setup}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

rpc_value() {
    local key="$1"
    awk -F= -v k="$key" '$1 == k {v=substr($0,index($0,"=")+1)} END{print v}' "$NODE_CONF"
}

setup_explorer() {
    command -v node >/dev/null || die "Node.js >=18 is required"
    [ -d "$SRC/lib" ] || die "materialized explorer missing; run scripts/materialize.sh"
    [ -f "$NODE_CONF" ] || die "node config missing; run scripts/testnet.sh init"

    if [ ! -d "$RUNTIME" ]; then
        mkdir -p "$RUNTIME"
        cp -a "$SRC/." "$RUNTIME/"
    fi

    RPC_USER="$(rpc_value rpcuser)"
    RPC_PASS="$(rpc_value rpcpassword)"
    [ -n "$RPC_USER" ] && [ -n "$RPC_PASS" ] || die "RPC credentials missing from $NODE_CONF"

    CONFIG="$CONFIG" RPC_USER="$RPC_USER" RPC_PASS="$RPC_PASS" python3 - <<'PY'
import json, os
from pathlib import Path
cfg = {
    'port': 8081,
    'bind': '127.0.0.1',
    'pollSeconds': 10,
    'siteName': 'Crakbit Testnet',
    'logLevel': 'info',
    'rpc': {
        'host': '127.0.0.1',
        'port': 29110,
        'user': os.environ['RPC_USER'],
        'password': os.environ['RPC_PASS'],
        'ssl': False,
        'timeout': 10000,
    },
}
Path(os.environ['CONFIG']).write_text(json.dumps(cfg, indent=2) + '\n')
PY
    chmod 600 "$CONFIG"
    log "explorer runtime prepared at $RUNTIME"
    log "default bind: http://127.0.0.1:8081"
}

case "$ACTION" in
    setup)
        setup_explorer
        ;;
    start)
        [ -f "$CONFIG" ] || setup_explorer
        log "starting Crakbit testnet explorer in foreground"
        cd "$RUNTIME"
        exec node server.js --config "$CONFIG"
        ;;
    *)
        echo "usage: scripts/explorer-testnet.sh {setup|start}" >&2
        exit 2
        ;;
esac
