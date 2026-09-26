#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
DAEMON="$BUILD_DIR/bin/crakbitd"
CLI="$BUILD_DIR/bin/crakbit-cli"
SCANNER="$BUILD_DIR/bin/crakminer-scan"
POOL="$ROOT/scripts/crakpool.py"
WORKER="$ROOT/scripts/crakminer-stratum.py"
TMP="$(mktemp -d)"
DATADIR="$TMP/datadir"
RPCPORT=19641
P2PPORT=19642
POOLPORT=19643
NODE_PID=""
POOL_PID=""

cleanup() {
  set +e
  if [[ -n "$POOL_PID" ]]; then
    kill "$POOL_PID" >/dev/null 2>&1 || true
    wait "$POOL_PID" >/dev/null 2>&1 || true
  fi
  "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" stop >/dev/null 2>&1 || true
  if [[ -n "$NODE_PID" ]]; then
    kill "$NODE_PID" >/dev/null 2>&1 || true
    wait "$NODE_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

for file in "$DAEMON" "$CLI" "$SCANNER"; do
  [[ -x "$file" ]] || { echo "missing executable: $file" >&2; exit 1; }
done
for file in "$POOL" "$WORKER"; do
  [[ -f "$file" ]] || { echo "missing CRAK-014 file: $file" >&2; exit 1; }
done

python3 -m py_compile "$POOL" "$WORKER"

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
NODE_PID=$!

for _ in $(seq 1 60); do
  if "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$NODE_PID" >/dev/null 2>&1; then
    echo "CRAK-014 node exited during startup" >&2
    cat "$TMP/node.log" >&2 || true
    exit 1
  fi
  sleep 1
done

"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" createwallet poolci >/dev/null

# Regtest network difficulty is ~4.66e-10. A 1e-9 share difficulty is harder,
# therefore every accepted share in this deterministic smoke is also a block.
python3 "$POOL" \
  --network regtest \
  --wallet poolci \
  --listen 127.0.0.1 \
  --port "$POOLPORT" \
  --share-difficulty 0.000000001 \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --scanner "$SCANNER" \
  >"$TMP/pool.log" 2>&1 &
POOL_PID=$!

for _ in $(seq 1 60); do
  if grep -Fq 'crakpool ready ' "$TMP/pool.log" 2>/dev/null; then
    break
  fi
  if ! kill -0 "$POOL_PID" >/dev/null 2>&1; then
    echo "CRAK-014 pool exited during startup" >&2
    cat "$TMP/pool.log" >&2 || true
    exit 1
  fi
  sleep 1
done

grep -F 'crakpool ready ' "$TMP/pool.log" >/dev/null

python3 "$WORKER" \
  --pool "127.0.0.1:$POOLPORT" \
  --worker ci.worker1 \
  --threads 2 \
  --cpu-limit 50 \
  --batch-hashes 64 \
  --shares 1 \
  --blocks 1 \
  --scanner "$SCANNER" \
  >"$TMP/worker1.log" 2>&1

HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
if [[ "$HEIGHT" != "1" ]]; then
  echo "CRAK-014 worker1 expected height 1, got $HEIGHT" >&2
  cat "$TMP/pool.log" >&2 || true
  cat "$TMP/worker1.log" >&2 || true
  exit 1
fi

python3 "$WORKER" \
  --pool "127.0.0.1:$POOLPORT" \
  --worker ci.worker2 \
  --threads 1 \
  --cpu-limit 100 \
  --batch-hashes 64 \
  --shares 1 \
  --blocks 1 \
  --scanner "$SCANNER" \
  >"$TMP/worker2.log" 2>&1

HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
if [[ "$HEIGHT" != "2" ]]; then
  echo "CRAK-014 worker2 expected height 2, got $HEIGHT" >&2
  cat "$TMP/pool.log" >&2 || true
  cat "$TMP/worker2.log" >&2 || true
  exit 1
fi

grep -F 'crakminer-stratum connected ' "$TMP/worker1.log" >/dev/null
grep -F 'crakminer-stratum accepted=1 ' "$TMP/worker1.log" >/dev/null
grep -F 'crakminer-stratum BLOCK blocks=1 ' "$TMP/worker1.log" >/dev/null
grep -F 'crakminer-stratum complete accepted=1 blocks=1 ' "$TMP/worker1.log" >/dev/null
grep -F 'crakminer-stratum accepted=1 ' "$TMP/worker2.log" >/dev/null
grep -F 'crakminer-stratum BLOCK blocks=1 ' "$TMP/worker2.log" >/dev/null
BLOCKS="$(grep -c 'crakpool BLOCK worker=ci.worker' "$TMP/pool.log" || true)"
if [[ "$BLOCKS" != "2" ]]; then
  echo "CRAK-014 expected two pool block submissions, got $BLOCKS" >&2
  cat "$TMP/pool.log" >&2 || true
  exit 1
fi

EXTRANONCES="$(grep 'crakpool connect peer=' "$TMP/pool.log" | sed -n 's/.*extranonce1=\([0-9a-f]*\).*/\1/p' | sort -u | wc -l)"
if (( EXTRANONCES < 2 )); then
  echo "CRAK-014 expected distinct extranonce1 values for two sessions" >&2
  cat "$TMP/pool.log" >&2 || true
  exit 1
fi

echo "CRAK-014 Stratum pool smoke: OK height=$HEIGHT blocks=$BLOCKS unique_extranonces=$EXTRANONCES"
