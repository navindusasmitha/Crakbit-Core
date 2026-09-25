#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR="${1:-.work/crakbit-build}"
DAEMON="$BUILD_DIR/bin/crakbitd"
CLI="$BUILD_DIR/bin/crakbit-cli"

[[ -x "$DAEMON" ]] || { echo "missing executable: $DAEMON" >&2; exit 1; }
[[ -x "$CLI" ]] || { echo "missing executable: $CLI" >&2; exit 1; }

ROOT="$(mktemp -d)"
declare -A DATADIR P2P RPC PID
P2P[1]=19601; RPC[1]=19701
P2P[2]=19602; RPC[2]=19702

cleanup() {
  set +e
  for i in 1 2; do
    if [[ -n "${DATADIR[$i]:-}" ]]; then
      "$CLI" -regtest -datadir="${DATADIR[$i]}" -rpcport="${RPC[$i]}" stop >/dev/null 2>&1 || true
    fi
  done
  sleep 1
  for i in 1 2; do
    if [[ -n "${PID[$i]:-}" ]]; then
      kill "${PID[$i]}" >/dev/null 2>&1 || true
      wait "${PID[$i]}" >/dev/null 2>&1 || true
    fi
  done
  rm -rf "$ROOT"
}
trap cleanup EXIT

cli() {
  local id="$1"; shift
  "$CLI" -regtest -datadir="${DATADIR[$id]}" -rpcport="${RPC[$id]}" "$@"
}

wallet_cli() {
  local id="$1" wallet="$2"; shift 2
  "$CLI" -regtest -datadir="${DATADIR[$id]}" -rpcport="${RPC[$id]}" -rpcwallet="$wallet" "$@"
}

wait_rpc() {
  local id="$1"
  for _ in $(seq 1 120); do
    if cli "$id" getblockcount >/dev/null 2>&1; then
      return 0
    fi
    if [[ -n "${PID[$id]:-}" ]] && ! kill -0 "${PID[$id]}" >/dev/null 2>&1; then
      echo "wallet node $id exited during startup" >&2
      tail -n 200 "${DATADIR[$id]}/regtest/debug.log" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "wallet node $id RPC did not become ready" >&2
  tail -n 200 "${DATADIR[$id]}/regtest/debug.log" >&2 || true
  return 1
}

wait_height() {
  local id="$1" expected="$2"
  for _ in $(seq 1 120); do
    if [[ "$(cli "$id" getblockcount 2>/dev/null || true)" == "$expected" ]]; then
      return 0
    fi
    sleep 1
  done
  echo "wallet node $id did not reach height $expected" >&2
  return 1
}

wait_connection() {
  local id="$1"
  for _ in $(seq 1 60); do
    local count
    count="$(cli "$id" getconnectioncount 2>/dev/null || echo 0)"
    if [[ "$count" =~ ^[0-9]+$ ]] && (( count >= 1 )); then
      return 0
    fi
    sleep 1
  done
  echo "wallet node $id did not establish a peer connection" >&2
  return 1
}

start_node() {
  local id="$1"
  DATADIR[$id]="${DATADIR[$id]:-$ROOT/node$id}"
  mkdir -p "${DATADIR[$id]}"
  "$DAEMON" \
    -regtest \
    -datadir="${DATADIR[$id]}" \
    -server=1 \
    -listen=1 \
    -bind=127.0.0.1 \
    -port="${P2P[$id]}" \
    -rpcbind=127.0.0.1 \
    -rpcallowip=127.0.0.1 \
    -rpcport="${RPC[$id]}" \
    -discover=0 \
    -dnsseed=0 \
    -fallbackfee=0.00001 \
    -printtoconsole=0 \
    >"${DATADIR[$id]}/node.log" 2>&1 &
  PID[$id]=$!
  wait_rpc "$id"
}

stop_node() {
  local id="$1"
  cli "$id" stop >/dev/null
  for _ in $(seq 1 60); do
    if ! kill -0 "${PID[$id]}" >/dev/null 2>&1; then
      wait "${PID[$id]}" >/dev/null 2>&1 || true
      PID[$id]=""
      return 0
    fi
    sleep 1
  done
  echo "wallet node $id did not stop cleanly" >&2
  return 1
}

start_node 1
start_node 2
cli 1 addnode "127.0.0.1:${P2P[2]}" onetry >/dev/null
wait_connection 1
wait_connection 2

cli 1 createwallet miner >/dev/null
cli 2 createwallet receiver >/dev/null
MINER_ADDR="$(wallet_cli 1 miner getnewaddress mining bech32)"
RECEIVER_ADDR="$(wallet_cli 2 receiver getnewaddress receive bech32)"

# Mine enough blocks for at least one 5 CRAK coinbase output to become mature.
wallet_cli 1 miner generatetoaddress 110 "$MINER_ADDR" 10000000 >/dev/null
wait_height 2 110

MATURE_BEFORE="$(wallet_cli 1 miner getbalance)"
python3 - "$MATURE_BEFORE" <<'PY'
from decimal import Decimal
import sys
value = Decimal(sys.argv[1])
if value < Decimal("5"):
    raise SystemExit(f"expected at least one mature 5 CRAK subsidy, got {value}")
PY

TXID="$(wallet_cli 1 miner sendtoaddress "$RECEIVER_ADDR" 1.0)"
[[ "$TXID" =~ ^[0-9a-f]{64}$ ]] || { echo "invalid wallet txid: $TXID" >&2; exit 1; }

# Confirm the payment and propagate it to the receiving wallet.
wallet_cli 1 miner generatetoaddress 1 "$MINER_ADDR" 10000000 >/dev/null
wait_height 2 111

for _ in $(seq 1 60); do
  if wallet_cli 2 receiver gettransaction "$TXID" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
TX_JSON="$(wallet_cli 2 receiver gettransaction "$TXID")"
python3 - "$TX_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
if int(obj.get("confirmations", 0)) < 1:
    raise SystemExit(f"receiver transaction is not confirmed: {obj}")
amount = obj.get("amount")
if amount is None or float(amount) < 0.99999999:
    raise SystemExit(f"receiver amount is not 1 CRAK: {obj}")
PY

BALANCE_BEFORE="$(wallet_cli 2 receiver getbalance)"
python3 - "$BALANCE_BEFORE" <<'PY'
from decimal import Decimal
import sys
value = Decimal(sys.argv[1])
if value < Decimal("1"):
    raise SystemExit(f"receiver balance before restart is too small: {value}")
PY

echo "CRAK-010: confirmed 1 CRAK wallet transfer txid=$TXID balance=$BALANCE_BEFORE"

# Clean restart must preserve the loaded wallet, transaction history, and balance.
stop_node 2
start_node 2

LOADED="$(cli 2 listwallets)"
python3 - "$LOADED" <<'PY'
import json
import sys
wallets = json.loads(sys.argv[1])
if "receiver" not in wallets:
    raise SystemExit(f"receiver wallet was not restored after restart: {wallets}")
PY

BALANCE_AFTER="$(wallet_cli 2 receiver getbalance)"
TX_AFTER="$(wallet_cli 2 receiver gettransaction "$TXID")"
python3 - "$BALANCE_BEFORE" "$BALANCE_AFTER" "$TX_AFTER" <<'PY'
from decimal import Decimal
import json
import sys
before = Decimal(sys.argv[1])
after = Decimal(sys.argv[2])
tx = json.loads(sys.argv[3])
if after != before:
    raise SystemExit(f"wallet balance changed across restart: before={before} after={after}")
if int(tx.get("confirmations", 0)) < 1:
    raise SystemExit(f"wallet transaction lost confirmation across restart: {tx}")
PY

echo "CRAK-010 wallet send/receive/restart smoke: OK balance=$BALANCE_AFTER txid=$TXID"
