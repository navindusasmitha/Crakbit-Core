#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${CRAKBIT_REFERENCE_TREE:-$ROOT/build/reference}"
SRC="$REF/pool"
RUNTIME="${CRAKBIT_POOL_DIR:-$ROOT/build/pool-testnet}"
DATA="${CRAKBIT_TESTNET_DATA:-$ROOT/build/testnet-data}"
NODE_CONF="$DATA/crakbit.conf"
CLI="$ROOT/build/dist/crakbit-cli"
CONFIG="$RUNTIME/config.crakbit-testnet.json"
ACTION="${1:-setup}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

need_node() {
    [ -x "$CLI" ] || die "build/dist/crakbit-cli missing; build the testnet first"
    [ -f "$NODE_CONF" ] || die "testnet config missing; run scripts/testnet.sh init"
    "$CLI" -datadir="$DATA" -conf="$NODE_CONF" getblockchaininfo >/dev/null \
        || die "testnet node is not running; run scripts/testnet.sh start"
}

rpc_value() {
    local key="$1"
    awk -F= -v k="$key" '$1 == k {v=substr($0,index($0,"=")+1)} END{print v}' "$NODE_CONF"
}

setup_pool() {
    need_node
    command -v node >/dev/null || die "Node.js >=18 is required"
    command -v npm >/dev/null || die "npm is required"
    [ -d "$SRC/lib" ] || die "materialized pool missing; run scripts/materialize.sh"
    [ -n "${CRAKBIT_REDIS_PASSWORD:-}" ] || die "set CRAKBIT_REDIS_PASSWORD to the same non-placeholder password configured as Redis requirepass"

    if [ ! -d "$RUNTIME" ]; then
        mkdir -p "$RUNTIME"
        cp -a "$SRC/." "$RUNTIME/"
    fi

    # Create/load a dedicated pool wallet and obtain a wallet-owned testnet
    # address. No payout-capable pool is allowed to use the burn placeholder.
    "$CLI" -datadir="$DATA" -conf="$NODE_CONF" createwallet pool >/dev/null 2>&1 || true
    POOL_ADDR="$("$CLI" -datadir="$DATA" -conf="$NODE_CONF" -rpcwallet=pool getnewaddress "" bech32)"
    [ -n "$POOL_ADDR" ] || die "could not obtain pool wallet address"

    RPC_USER="$(rpc_value rpcuser)"
    RPC_PASS="$(rpc_value rpcpassword)"
    [ -n "$RPC_USER" ] && [ -n "$RPC_PASS" ] || die "RPC credentials missing from $NODE_CONF"

    cp "$RUNTIME/config.testnet.json" "$CONFIG"
    CONFIG="$CONFIG" POOL_ADDR="$POOL_ADDR" RPC_USER="$RPC_USER" RPC_PASS="$RPC_PASS" \
      REDIS_PASS="$CRAKBIT_REDIS_PASSWORD" python3 - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ['CONFIG'])
cfg = json.loads(p.read_text())
cfg['network'] = 'testnet'
cfg['poolAddress'] = os.environ['POOL_ADDR']
cfg['coinbaseSignature'] = '/Crakbit-Testnet/'
cfg['redis']['password'] = os.environ['REDIS_PASS']
cfg['redis']['db'] = 1
cfg['redisPrefix'] = 'cbittn'
cfg['daemons'] = [{
    'host': '127.0.0.1',
    'port': 29110,
    'user': os.environ['RPC_USER'],
    'password': os.environ['RPC_PASS'],
    'wallet': 'pool',
    'timeout': 15000,
}]
cfg['ports'] = [{
    'port': 3334,
    'difficulty': 0.0001,
    'description': 'Crakbit testnet CPU port',
}]
cfg['apiPort'] = 8082
p.write_text(json.dumps(cfg, indent=2) + '\n')
PY
    chmod 600 "$CONFIG"

    log "install pool dependencies"
    (cd "$RUNTIME" && npm install)
    log "build RandomX native addon"
    (cd "$RUNTIME" && \
      RANDOMX_INCLUDE="$REF/build/randomx/src" \
      RANDOMX_LIB="$REF/build/randomx/build/librandomx.a" \
      npm run build:native)
    log "run pool accounting tests"
    (cd "$RUNTIME" && npm test)

    printf 'Pool address: %s\n' "$POOL_ADDR"
    printf 'Stratum:     tcp://0.0.0.0:3334\n'
    printf 'API:         http://0.0.0.0:8082\n'
    printf 'Config:      %s\n' "$CONFIG"
}

case "$ACTION" in
    setup)
        setup_pool
        ;;
    test)
        [ -d "$RUNTIME/node_modules" ] || setup_pool
        (cd "$RUNTIME" && npm test)
        ;;
    start)
        need_node
        [ -f "$CONFIG" ] || die "run: CRAKBIT_REDIS_PASSWORD=... scripts/pool-testnet.sh setup"
        log "starting Crakbit Stratum pool in foreground"
        cd "$RUNTIME"
        exec node server.js --config "$CONFIG"
        ;;
    *)
        echo "usage: scripts/pool-testnet.sh {setup|test|start}" >&2
        exit 2
        ;;
esac
