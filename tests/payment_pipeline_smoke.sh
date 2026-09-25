#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
DAEMON="$BUILD_DIR/bin/crakbitd"
CLI="$BUILD_DIR/bin/crakbit-cli"
SCANNER="$BUILD_DIR/bin/crakminer-scan"
POOL="$ROOT/scripts/crakpool-accounting.py"
WORKER="$ROOT/scripts/crakminer-stratum.py"
PLANNER="$ROOT/scripts/crakpool-payout.py"
PAY="$ROOT/scripts/crakpool-pay.py"
TMP="$(mktemp -d)"
DATADIR="$TMP/datadir"
DB="$TMP/pool.sqlite3"
RPCPORT=19671
P2PPORT=19672
POOLPORT=19673
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
for file in "$POOL" "$WORKER" "$PLANNER" "$PAY"; do
  [[ -f "$file" ]] || { echo "missing CRAK-017 file: $file" >&2; exit 1; }
done

python3 -m py_compile "$POOL" "$WORKER" "$PLANNER" "$PAY"
mkdir -p "$DATADIR"

start_node() {
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
      return 0
    fi
    if ! kill -0 "$NODE_PID" >/dev/null 2>&1; then
      echo "CRAK-017 node exited during startup" >&2
      cat "$TMP/node.log" >&2 || true
      exit 1
    fi
    sleep 1
  done
  echo "CRAK-017 node did not become ready" >&2
  exit 1
}

stop_node() {
  "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" stop >/dev/null
  if [[ -n "$NODE_PID" ]]; then
    wait "$NODE_PID" >/dev/null 2>&1 || true
    NODE_PID=""
  fi
}

ensure_wallet_loaded() {
  local wallet="$1"
  if "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet="$wallet" getwalletinfo >/dev/null 2>&1; then
    return 0
  fi
  "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" loadwallet "$wallet" >/dev/null
  "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet="$wallet" getwalletinfo >/dev/null
}

start_node
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
  --pool-fee-bps 100 \
  >"$TMP/pool.log" 2>&1 &
POOL_PID=$!

for _ in $(seq 1 60); do
  if grep -Fq 'crakpool ready ' "$TMP/pool.log" 2>/dev/null; then
    break
  fi
  if ! kill -0 "$POOL_PID" >/dev/null 2>&1; then
    echo "CRAK-017 pool exited during startup" >&2
    cat "$TMP/pool.log" >&2 || true
    exit 1
  fi
  sleep 1
done

grep -F 'crakpool ready ' "$TMP/pool.log" >/dev/null

python3 "$WORKER" \
  --pool "127.0.0.1:$POOLPORT" \
  --worker pay.worker \
  --threads 1 \
  --cpu-limit 100 \
  --batch-hashes 64 \
  --shares 1 \
  --blocks 1 \
  --scanner "$SCANNER" \
  >"$TMP/worker.log" 2>&1

HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
[[ "$HEIGHT" == "1" ]] || { echo "CRAK-017 expected pool block at height 1, got $HEIGHT" >&2; exit 1; }

kill "$POOL_PID" >/dev/null 2>&1 || true
wait "$POOL_PID" >/dev/null 2>&1 || true
POOL_PID=""

python3 "$PLANNER" --db "$DB" register \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --worker pay.worker \
  --address "$WORKER_ADDRESS" \
  >/dev/null

# The credited pool block distributes 99% = 4.95 CRAK to the worker. The
# retained 1% gives the pool wallet room to pay the transaction fee without
# subtracting any fee from the worker's credited amount.
for _ in $(seq 1 100); do
  "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci \
    generatetoaddress 1 "$POOL_ADDRESS" 1000000 >/dev/null
done
HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
[[ "$HEIGHT" == "101" ]] || { echo "CRAK-017 expected maturity height 101, got $HEIGHT" >&2; exit 1; }

python3 "$PLANNER" --db "$DB" plan \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --maturity 100 \
  --minimum-sats 1 \
  --max-outputs 10 \
  --wallet poolci \
  --fee-reserve-sats 100000 \
  >"$TMP/plan.json"

BATCH_ID="$(python3 - "$TMP/plan.json" "$WORKER_ADDRESS" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
b = j['batch']
assert b is not None, j
assert b['state'] == 'planned', b
assert b['total_sats'] == 495_000_000, b
assert b['outputs'] == [{'worker': 'pay.worker', 'address': sys.argv[2], 'amount_sats': 495_000_000}], b
print(b['id'])
PY
)"

python3 "$PAY" --db "$DB" prepare \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --batch "$BATCH_ID" \
  --wallet poolci \
  --fee-rate 1.0 \
  --max-fee-sats 100000 \
  --confirmations 1 \
  >"$TMP/prepared.json"

TXID="$(python3 - "$TMP/prepared.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['broadcast'] is False, j
assert j['batch']['state'] == 'prepared', j
assert j['transaction']['state'] == 'prepared', j
assert 0 < j['transaction']['fee_sats'] <= 100000, j
print(j['transaction']['txid'])
PY
)"

python3 - "$DB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
assert con.execute("SELECT SUM(amount_sats) FROM credits WHERE status='paying'").fetchone()[0] == 495_000_000
assert con.execute("SELECT state FROM payout_batches").fetchone()[0] == 'prepared'
assert con.execute("SELECT state FROM payout_transactions").fetchone()[0] == 'prepared'
con.close()
PY

# Restart the node between signing and broadcast. CRAK-017 must recover from
# the SQLite-persisted raw transaction instead of building a different spend.
stop_node
start_node
ensure_wallet_loaded poolci
ensure_wallet_loaded workerci

python3 "$PAY" --db "$DB" sync \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --batch "$BATCH_ID" \
  >"$TMP/recovered.json"
python3 - "$TMP/recovered.json" "$TXID" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))['results'][0]
assert j['state'] == 'prepared', j
assert j['txid'] == sys.argv[2], j
assert j['action'] == 'ready', j
PY

python3 "$PAY" --db "$DB" broadcast \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --batch "$BATCH_ID" \
  >"$TMP/broadcast.json"
python3 - "$TMP/broadcast.json" "$TXID" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['broadcast'] is True, j
assert j['batch']['state'] == 'broadcast', j
assert j['transaction']['state'] == 'broadcast', j
assert j['transaction']['txid'] == sys.argv[2], j
PY

"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getmempoolentry "$TXID" >/dev/null
"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci \
  generatetoaddress 1 "$POOL_ADDRESS" 1000000 >/dev/null

python3 "$PAY" --db "$DB" sync \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --batch "$BATCH_ID" \
  >"$TMP/paid.json"
python3 - "$TMP/paid.json" "$TXID" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))['results'][0]
assert j['state'] == 'paid', j
assert j['txid'] == sys.argv[2], j
assert j['confirmations'] >= 1, j
assert j['action'] == 'finalized', j
PY

python3 - "$DB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
assert con.execute("SELECT SUM(amount_sats) FROM credits WHERE status='paid'").fetchone()[0] == 495_000_000
assert con.execute("SELECT state FROM payout_batches").fetchone()[0] == 'paid'
row = con.execute("SELECT state,confirmations,fee_sats FROM payout_transactions").fetchone()
assert row[0] == 'paid', row
assert row[1] >= 1, row
assert 0 < row[2] <= 100000, row
con.close()
PY

RECEIVED="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=workerci getreceivedbyaddress "$WORKER_ADDRESS" 1)"
python3 - "$RECEIVED" <<'PY'
from decimal import Decimal
import sys
assert Decimal(sys.argv[1]) == Decimal('4.95000000'), sys.argv[1]
PY

echo "CRAK-017 signed payout smoke: OK batch=$BATCH_ID txid=$TXID paid_sats=495000000 restart_recovery=1"
