#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
DAEMON="$BUILD_DIR/bin/crakbitd"
CLI="$BUILD_DIR/bin/crakbit-cli"
SCANNER="$BUILD_DIR/bin/crakminer-scan"
CONTROLLER="$ROOT/scripts/crakminer-native.py"
TMP="$(mktemp -d)"
DATADIR="$TMP/datadir"
RPCPORT=19631
P2PPORT=19632

cleanup() {
  set +e
  "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" stop >/dev/null 2>&1 || true
  if [[ -n "${PID:-}" ]]; then
    kill "$PID" >/dev/null 2>&1 || true
    wait "$PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

for file in "$DAEMON" "$CLI" "$SCANNER"; do
  [[ -x "$file" ]] || { echo "missing executable: $file" >&2; exit 1; }
done
[[ -f "$CONTROLLER" ]] || { echo "missing controller: $CONTROLLER" >&2; exit 1; }

mkdir -p "$DATADIR"
"$DAEMON" \
  -regtest \
  "-datadir=$DATADIR" \
  -server=1 \
  -listen=1 \
  -bind=127.0.0.1 \
  "-port=$P2PPORT" \
  -rpcbind=127.0.0.1 \
  -rpcallowip=127.0.0.1 \
  "-rpcport=$RPCPORT" \
  -connect=0 \
  -discover=0 \
  -dnsseed=0 \
  -printtoconsole=0 \
  >"$TMP/node.log" 2>&1 &
PID=$!

for _ in $(seq 1 60); do
  if "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    echo "CRAK-013 node exited during startup" >&2
    cat "$TMP/node.log" >&2 || true
    exit 1
  fi
  sleep 1
done

"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" createwallet nativeci >/dev/null

python3 "$CONTROLLER" \
  --network regtest \
  --wallet nativeci \
  --threads 2 \
  --cpu-limit 50 \
  --blocks 1 \
  --batch-hashes 64 \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --scanner "$SCANNER" \
  >"$TMP/miner.log"

HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
if [[ "$HEIGHT" != "1" ]]; then
  echo "CRAK-013 expected native miner height 1, got $HEIGHT" >&2
  cat "$TMP/miner.log" >&2 || true
  exit 1
fi

grep -F 'crakminer-native accepted=1 ' "$TMP/miner.log" >/dev/null
grep -F 'crakminer-native complete accepted=1' "$TMP/miner.log" >/dev/null

echo "CRAK-013 native getblocktemplate miner smoke: OK height=$HEIGHT"
