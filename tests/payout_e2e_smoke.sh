#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
DAEMON="$BUILD_DIR/bin/crakbitd"
CLI="$BUILD_DIR/bin/crakbit-cli"
SCANNER="$BUILD_DIR/bin/crakminer-scan"
POOL="$ROOT/scripts/crakpool-accounting.py"
WORKER="$ROOT/scripts/crakminer-stratum.py"
PAYOUT="$ROOT/scripts/crakpool-payout.py"
PAYTX="$ROOT/scripts/crakpool-paytx.py"
PAYGUARD="$ROOT/scripts/crakpool-payguard.py"
PAYOPS="$ROOT/scripts/crakpool-payops.py"
TMP="$(mktemp -d)"
DATADIR="$TMP/datadir"
DB="$TMP/pool.sqlite3"
RPCPORT=19761
P2PPORT=19762
POOLPORT=19763
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
for file in "$POOL" "$WORKER" "$PAYOUT" "$PAYTX" "$PAYGUARD" "$PAYOPS"; do
  [[ -f "$file" ]] || { echo "missing CRAK payout file: $file" >&2; exit 1; }
done

python3 -m py_compile "$POOL" "$WORKER" "$PAYOUT" "$PAYTX" "$PAYGUARD" "$PAYOPS"
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
    echo "CRAK-020 node exited during startup" >&2
    cat "$TMP/node.log" >&2 || true
    exit 1
  fi
  sleep 1
done

"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" createwallet poolci >/dev/null
"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" createwallet workerci >/dev/null
POOL_ADDRESS="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci getnewaddress '' bech32)"
WORKER_ADDRESS="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=workerci getnewaddress '' bech32)"

# Pre-fund the pool wallet with a separate coinbase so the payout output can
# remain the exact 5 CRAK block credit while the transaction fee is paid from
# another mature UTXO.
"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci \
  generatetoaddress 1 "$POOL_ADDRESS" 1000000 >/dev/null

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
    echo "CRAK-020 pool exited during startup" >&2
    cat "$TMP/pool.log" >&2 || true
    exit 1
  fi
  sleep 1
done

grep -F 'crakpool ready ' "$TMP/pool.log" >/dev/null

python3 "$WORKER" \
  --pool "127.0.0.1:$POOLPORT" \
  --worker e2e.worker \
  --threads 1 \
  --cpu-limit 100 \
  --batch-hashes 64 \
  --shares 1 \
  --blocks 1 \
  --scanner "$SCANNER" \
  >"$TMP/worker.log" 2>&1

HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
[[ "$HEIGHT" == "2" ]] || { echo "CRAK-020 expected pool block at height 2, got $HEIGHT" >&2; exit 1; }

kill "$POOL_PID" >/dev/null 2>&1 || true
wait "$POOL_PID" >/dev/null 2>&1 || true
POOL_PID=""

python3 "$PAYOUT" --db "$DB" register \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --worker e2e.worker \
  --address "$WORKER_ADDRESS" \
  >"$TMP/register.json"

# Mine 99 descendants: height-2 pool coinbase reaches 100 confirmations, while
# the height-1 funding coinbase is also mature and can cover the payout fee.
for _ in $(seq 1 99); do
  "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci \
    generatetoaddress 1 "$POOL_ADDRESS" 1000000 >/dev/null
done
HEIGHT="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" getblockcount)"
[[ "$HEIGHT" == "101" ]] || { echo "CRAK-020 expected maturity height 101, got $HEIGHT" >&2; exit 1; }

python3 "$PAYOUT" --db "$DB" plan \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --maturity 100 \
  --minimum-sats 1 \
  --max-outputs 10 \
  >"$TMP/plan.json"

BATCH_ID="$(python3 - "$TMP/plan.json" "$WORKER_ADDRESS" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
b = j['batch']
assert b is not None, j
assert b['state'] == 'planned', b
assert b['total_sats'] == 500_000_000, b
assert b['outputs'] == [{'worker': 'e2e.worker', 'address': sys.argv[2], 'amount_sats': 500_000_000}], b
print(b['id'])
PY
)"

python3 "$PAYTX" --db "$DB" build-psbt \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --wallet poolci \
  --batch "$BATCH_ID" \
  --fee-rate 1.0 \
  >"$TMP/psbt.json"

PSBT="$(python3 - "$TMP/psbt.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['state'] == 'psbt_ready', j
assert j['txid'] is None, j
assert j['estimated_fee_sats'] is not None and j['estimated_fee_sats'] > 0, j
print(j['psbt'])
PY
)"

python3 "$PAYGUARD" --db "$DB" preflight \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --wallet poolci \
  --batch "$BATCH_ID" \
  --max-fee-sats 100000 \
  >"$TMP/preflight.json"
python3 - "$TMP/preflight.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['safe_to_sign_and_broadcast_externally'] is True, j
assert j['preflight']['valid'] is True, j
assert j['input_count'] >= 1, j
PY

# CRAK-020 intentionally performs signing/broadcast only inside this isolated
# regtest CI smoke. Runtime/operator tools retain CRAK-017/018 manual custody.
"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci \
  walletprocesspsbt "$PSBT" >"$TMP/signed.json"
SIGNED_PSBT="$(python3 - "$TMP/signed.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['complete'] is True, j
print(j['psbt'])
PY
)"

"$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" \
  finalizepsbt "$SIGNED_PSBT" >"$TMP/final.json"
RAW_HEX="$(python3 - "$TMP/final.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['complete'] is True, j
print(j['hex'])
PY
)"

TXID="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" sendrawtransaction "$RAW_HEX")"
[[ "${#TXID}" == "64" ]] || { echo "CRAK-020 invalid txid: $TXID" >&2; exit 1; }

python3 "$PAYGUARD" --db "$DB" guarded-attach \
  --batch "$BATCH_ID" \
  --txid "$TXID" \
  >"$TMP/attach.json"
python3 - "$TMP/attach.json" "$TXID" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['state'] == 'broadcast', j
assert j['txid'] == sys.argv[2], j
PY

python3 "$PAYOPS" --db "$DB" show --batch "$BATCH_ID" >"$TMP/show-broadcast.json"
python3 - "$TMP/show-broadcast.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['state'] == 'broadcast', j
assert j['next_action'] == 'wait_confirmations', j
PY

for _ in $(seq 1 6); do
  "$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=poolci \
    generatetoaddress 1 "$POOL_ADDRESS" 1000000 >/dev/null
done

python3 "$PAYOPS" --db "$DB" refresh \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --wallet poolci \
  --batch "$BATCH_ID" \
  >"$TMP/refreshed.json"
python3 - "$TMP/refreshed.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['state'] == 'confirmed', j
assert j['confirmations'] >= 6, j
assert j['next_action'] == 'settle', j
PY

python3 "$PAYTX" --db "$DB" settle \
  --network regtest \
  --datadir "$DATADIR" \
  --rpcport "$RPCPORT" \
  --cli "$CLI" \
  --wallet poolci \
  --batch "$BATCH_ID" \
  --confirmations 6 \
  >"$TMP/settled.json"
python3 - "$TMP/settled.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['state'] == 'paid', j
assert j['confirmations'] >= 6, j
PY

python3 "$PAYOPS" --db "$DB" summary >"$TMP/summary.json"
python3 - "$TMP/summary.json" <<'PY'
import json, sys
j = json.load(open(sys.argv[1], encoding='utf-8'))
assert j['batches'] == 1, j
assert j['states'].get('paid') == 1, j
assert j['next_actions'].get('done') == 1, j
PY

WORKER_BALANCE="$("$CLI" -regtest "-datadir=$DATADIR" "-rpcport=$RPCPORT" -rpcwallet=workerci getbalance)"
python3 - "$WORKER_BALANCE" <<'PY'
from decimal import Decimal
import sys
assert Decimal(sys.argv[1]) == Decimal('5.00000000'), sys.argv[1]
PY

echo "CRAK-020 payout E2E regtest smoke: OK batch=$BATCH_ID txid=$TXID confirmations>=6 paid=true worker_balance=$WORKER_BALANCE"
