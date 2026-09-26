#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
DAEMON="$BUILD_DIR/bin/crakbitd"
CLI="$BUILD_DIR/bin/crakbit-cli"
SCANNER="$BUILD_DIR/bin/crakminer-scan"
POOL="$ROOT/scripts/crakpool-accounting.py"
WORKER="$ROOT/scripts/crakminer-stratum.py"
PAYOUT_TOOL="$ROOT/scripts/crakpool-payout.py"
TMP="$(mktemp -d)"
DATADIR="$TMP/datadir"
DB="$TMP/pool.sqlite3"
RPCPORT=19661
P2PPORT=19662
POOLPORT=19663
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
for file in "$POOL" "$WORKER" "$PAYOUT_TOOL"; do
  [[ -f "$file" ]] || { echo "missing CRAK-016 file: $file" >&2; exit 1; }
done

python3 -m py_compile "$POOL" "$WORKER" "$PAYOUT_TOOL"
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
    echo "CRAK-016 node exited during startup" >&2
    cat "$TMP/node.log" >&2 || true
    exit 1
  fi
  sleep 1
done

"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" createwallet poolci >/dev/null
"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" createwallet workerci >/dev/null
POOL_ADDRESS="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci getnewaddress '' bech32)"
WORKER_ADDRESS="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=workerci getnewaddress '' bech32)"

python3 "$POOL" \
  --network regtest \
  --address "$POOL_ADDRESS" \
  --listen 127.0.0.1 \
  --port "$POOLPORT" \
  --share-difficulty 0.000000001 \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --scanner "$SCANNER" \
  --db "$DB" \
  --payout-mode proportional \
  --pool-fee-bps 0 \
  >"$TMP/pool.log" 2>&1 &
POOL_PID=$!

for _ in $(seq 1 60); do
  if grep -Fq 'crakpool ready ' "$TMP/pool.log" 2>/dev/null; then
    break
  fi
  if ! kill -0 "$POOL_PID" >/dev/null 2>&1; then
    echo "CRAK-016 pool exited during startup" >&2
    cat "$TMP/pool.log" >&2 || true
    exit 1
  fi
  sleep 1
done

grep -F 'crakpool ready ' "$TMP/pool.log" >/dev/null

python3 "$WORKER" \
  --pool "127.0.0.1:$POOLPORT" \
  --worker payout.worker \
  --threads 1 \
  --cpu-limit 100 \
  --batch-hashes 64 \
  --shares 1 \
  --blocks 1 \
  --scanner "$SCANNER" \
  >"$TMP/worker.log" 2>&1

HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
[[ "$HEIGHT" == "1" ]] || { echo "CRAK-016 expected height 1 after pool block, got $HEIGHT" >&2; exit 1; }

kill "$POOL_PID" >/dev/null 2>&1 || true
wait "$POOL_PID" >/dev/null 2>&1 || true
POOL_PID=""

BLOCK_HASH="$(python3 - "$DB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
row = con.execute("SELECT hash FROM blocks WHERE height=1").fetchone()
assert row is not None
print(row[0])
con.close()
PY
)"

python3 "$PAYOUT_TOOL" --db "$DB" register \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --worker payout.worker \
  --address "$WORKER_ADDRESS" \
  >"$TMP/register.json"

# At height 1, the found coinbase has only one confirmation and must not enter
# a maturity-100 payout batch.
python3 "$PAYOUT_TOOL" --db "$DB" plan \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --maturity 100 \
  --minimum-sats 1 \
  --max-outputs 10 \
  >"$TMP/immature.json"
python3 - "$TMP/immature.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding="utf-8"))
assert j["broadcast_enabled"] is False, j
assert j["batch"] is None, j
assert j["reconciliation"]["canonical_blocks"] == 1, j
PY

# Mine 99 descendants. The pool block at height 1 now has 100 confirmations.
for _ in $(seq 1 99); do
  "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci \
    generatetoaddress 1 "$POOL_ADDRESS" 1000000 >/dev/null
done
HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
[[ "$HEIGHT" == "100" ]] || { echo "CRAK-016 expected maturity height 100, got $HEIGHT" >&2; exit 1; }

python3 "$PAYOUT_TOOL" --db "$DB" plan \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --maturity 100 \
  --minimum-sats 1 \
  --max-outputs 10 \
  >"$TMP/mature.json"

BATCH_ID="$(python3 - "$TMP/mature.json" "$WORKER_ADDRESS" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding="utf-8"))
assert j["broadcast_enabled"] is False, j
b = j["batch"]
assert b is not None, j
assert b["state"] == "planned", b
assert b["total_sats"] == 500_000_000, b
assert b["output_count"] == 1, b
assert b["outputs"] == [{"worker": "payout.worker", "address": sys.argv[2], "amount_sats": 500_000_000}], b
print(b["id"])
PY
)"

# Simulate a reorg by invalidating the credited height-1 block. The node drops
# that block and all descendants, and reconciliation must invalidate the plan.
"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" invalidateblock "$BLOCK_HASH" >/dev/null
HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
[[ "$HEIGHT" == "0" ]] || { echo "CRAK-016 expected height 0 after invalidating block 1, got $HEIGHT" >&2; exit 1; }

python3 "$PAYOUT_TOOL" --db "$DB" reconcile \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  >"$TMP/reorg.json"
python3 "$PAYOUT_TOOL" --db "$DB" show --batch "$BATCH_ID" >"$TMP/batch.json"
python3 "$PAYOUT_TOOL" --db "$DB" status >"$TMP/status.json"

python3 - "$TMP/reorg.json" "$TMP/batch.json" "$TMP/status.json" "$BATCH_ID" <<'PY'
import json, sys
reorg = json.load(open(sys.argv[1], encoding="utf-8"))
batch = json.load(open(sys.argv[2], encoding="utf-8"))
status = json.load(open(sys.argv[3], encoding="utf-8"))
batch_id = sys.argv[4]
assert reorg["canonical_blocks"] == 0, reorg
assert reorg["orphaned_blocks"] == 1, reorg
assert batch_id in reorg["invalidated_batches"], reorg
assert batch["state"] == "invalidated", batch
assert status["credits"]["orphaned"]["sats"] == 500_000_000, status
assert status["batches"]["invalidated"] == 1, status
PY

echo "CRAK-016 payout planner smoke: OK mature_height=100 reorg_height=0 batch=$BATCH_ID broadcast=false"
