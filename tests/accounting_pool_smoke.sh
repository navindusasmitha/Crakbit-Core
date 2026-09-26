#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
DAEMON="$BUILD_DIR/bin/crakbitd"
CLI="$BUILD_DIR/bin/crakbit-cli"
SCANNER="$BUILD_DIR/bin/crakminer-scan"
POOL="$ROOT/scripts/crakpool-accounting.py"
WORKER="$ROOT/scripts/crakminer-stratum.py"
STATS="$ROOT/scripts/crakpool-stats.py"
TMP="$(mktemp -d)"
DATADIR="$TMP/datadir"
DB="$TMP/pool.sqlite3"
RPCPORT=19651
P2PPORT=19652
POOLPORT=19653
NODE_PID=""
POOL_PID=""
POOL_RUN=0

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
for file in "$POOL" "$WORKER" "$STATS"; do
  [[ -f "$file" ]] || { echo "missing CRAK-015 file: $file" >&2; exit 1; }
done

python3 -m py_compile "$POOL" "$WORKER" "$STATS"
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
    echo "CRAK-015 node exited during startup" >&2
    cat "$TMP/node.log" >&2 || true
    exit 1
  fi
  sleep 1
done

"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" createwallet poolci >/dev/null
PAYOUT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci getnewaddress '' bech32)"

start_pool() {
  POOL_RUN=$((POOL_RUN + 1))
  local log="$TMP/pool-$POOL_RUN.log"
  python3 "$POOL" \
    --network regtest \
    --address "$PAYOUT" \
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
    >"$log" 2>&1 &
  POOL_PID=$!
  for _ in $(seq 1 60); do
    if grep -Fq 'crakpool ready ' "$log" 2>/dev/null; then
      return 0
    fi
    if ! kill -0 "$POOL_PID" >/dev/null 2>&1; then
      echo "CRAK-015 pool exited during startup" >&2
      cat "$log" >&2 || true
      exit 1
    fi
    sleep 1
  done
  echo "CRAK-015 pool did not become ready" >&2
  cat "$log" >&2 || true
  exit 1
}

stop_pool() {
  if [[ -n "$POOL_PID" ]]; then
    kill "$POOL_PID" >/dev/null 2>&1 || true
    wait "$POOL_PID" >/dev/null 2>&1 || true
    POOL_PID=""
    sleep 1
  fi
}

start_pool
python3 "$WORKER" \
  --pool "127.0.0.1:$POOLPORT" \
  --worker accounting.worker1 \
  --threads 1 \
  --cpu-limit 100 \
  --batch-hashes 64 \
  --shares 1 \
  --blocks 1 \
  --scanner "$SCANNER" \
  >"$TMP/worker1.log" 2>&1

HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
[[ "$HEIGHT" == "1" ]] || { echo "CRAK-015 expected height 1 after worker1, got $HEIGHT" >&2; exit 1; }

# Restart the pool process but keep the same DB. CRAK-015 must recover worker,
# block and pending-credit accounting from SQLite rather than process memory.
stop_pool
start_pool

python3 "$WORKER" \
  --pool "127.0.0.1:$POOLPORT" \
  --worker accounting.worker2 \
  --threads 2 \
  --cpu-limit 50 \
  --batch-hashes 64 \
  --shares 1 \
  --blocks 1 \
  --scanner "$SCANNER" \
  >"$TMP/worker2.log" 2>&1

HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
[[ "$HEIGHT" == "2" ]] || { echo "CRAK-015 expected height 2 after worker2, got $HEIGHT" >&2; exit 1; }

python3 "$STATS" --db "$DB" --window 600 --json >"$TMP/stats.json"
python3 - "$TMP/stats.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
assert s["blocks"] == 2, s
assert s["reward_sats"] == 1_000_000_000, s
assert s["pool_fee_sats"] == 0, s
assert s["credited_sats"] == 1_000_000_000, s
assert s["pending_sats"] == 1_000_000_000, s
workers = {row["worker"]: row for row in s["workers"]}
assert set(workers) == {"accounting.worker1", "accounting.worker2"}, workers
for name in workers:
    assert workers[name]["accepted_shares"] == 1, workers[name]
    assert workers[name]["rejected_shares"] == 0, workers[name]
    assert workers[name]["pending_sats"] == 500_000_000, workers[name]
    assert workers[name]["estimated_hashrate_hs"] > 0, workers[name]
PY

python3 - "$DB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
blocks = con.execute("SELECT height, reward_sats, payout_mode, start_share_id, end_share_id FROM blocks ORDER BY height").fetchall()
assert blocks == [(1, 500_000_000, "proportional", 1, 1), (2, 500_000_000, "proportional", 2, 2)], blocks
credits = con.execute("SELECT worker, SUM(amount_sats) FROM credits GROUP BY worker ORDER BY worker").fetchall()
assert credits == [("accounting.worker1", 500_000_000), ("accounting.worker2", 500_000_000)], credits
con.close()
PY

grep -F 'accounting_db=' "$TMP/pool-1.log" >/dev/null
grep -F 'payout_mode=proportional' "$TMP/pool-2.log" >/dev/null
grep -F 'crakminer-stratum accepted=1 ' "$TMP/worker1.log" >/dev/null
grep -F 'crakminer-stratum accepted=1 ' "$TMP/worker2.log" >/dev/null

echo "CRAK-015 accounting pool smoke: OK height=$HEIGHT pending_sats=1000000000 restart=1"
