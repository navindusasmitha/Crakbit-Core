#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${CRAKBIT_DIST:-$ROOT/build/dist}"
DATA="${CRAKBIT_TESTNET_DATA:-$ROOT/build/testnet-data}"
CONF="$DATA/crakbit.conf"
NODE="$DIST/crakbitd"
CLI="$DIST/crakbit-cli"
ACTION="${1:-status}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ -x "$NODE" ] || die "missing $NODE; run scripts/materialize.sh and scripts/build-testnet.sh"
[ -x "$CLI" ] || die "missing $CLI"

init_conf() {
    mkdir -p "$DATA"
    if [ ! -f "$CONF" ]; then
        cat > "$CONF" <<'EOF'
# Crakbit testnet-v0.1
server=1
txindex=1
listen=1
maxconnections=125
dbcache=450

[test]
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
rpcport=29110
port=29111
EOF
        chmod 600 "$CONF"
        log "created $CONF"
    fi

    # Optional explicit first peer for the seedless initial testnet.
    if [ -n "${CRAKBIT_ADDNODE:-}" ] && ! grep -Fqx "addnode=$CRAKBIT_ADDNODE" "$CONF"; then
        printf 'addnode=%s\n' "$CRAKBIT_ADDNODE" >> "$CONF"
        log "added bootstrap peer $CRAKBIT_ADDNODE"
    fi
}

cli() {
    "$CLI" -datadir="$DATA" -conf="$CONF" "${@:1}"
}

case "$ACTION" in
    init)
        init_conf
        ;;
    start)
        init_conf
        log "starting Crakbit testnet node"
        "$NODE" -datadir="$DATA" -conf="$CONF" -daemon
        sleep 1
        cli getblockchaininfo
        ;;
    stop)
        init_conf
        cli stop
        ;;
    status)
        init_conf
        cli getblockchaininfo
        ;;
    peers)
        init_conf
        cli getpeerinfo
        ;;
    wallet)
        init_conf
        name="${2:-default}"
        cli createwallet "$name" 2>/dev/null || true
        cli -rpcwallet="$name" getwalletinfo
        ;;
    address)
        init_conf
        name="${2:-default}"
        cli createwallet "$name" 2>/dev/null || true
        cli -rpcwallet="$name" getnewaddress "" bech32
        ;;
    cli)
        shift
        init_conf
        cli "$@"
        ;;
    *)
        cat >&2 <<EOF
usage: scripts/testnet.sh {init|start|stop|status|peers|wallet [name]|address [name]|cli ...}

Optional environment:
  CRAKBIT_ADDNODE=host:29111     first peer for the initial seedless testnet
  CRAKBIT_TESTNET_DATA=/path     alternate data directory
EOF
        exit 2
        ;;
esac
