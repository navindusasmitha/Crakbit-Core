#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR="${1:-.work/crakbit-full-build}"
DAEMON="$BUILD_DIR/bin/crakbitd"
CLI="$BUILD_DIR/bin/crakbit-cli"

[[ -x "$DAEMON" ]] || { echo "missing executable: $DAEMON" >&2; exit 1; }
[[ -x "$CLI" ]] || { echo "missing executable: $CLI" >&2; exit 1; }

ROOT="$(mktemp -d)"
declare -A DATADIR P2P RPC PID
P2P[1]=19401; RPC[1]=19501
P2P[2]=19402; RPC[2]=19502
P2P[3]=19403; RPC[3]=19503

cleanup() {
  set +e
  for i in 1 2 3; do
    if [[ -n "${DATADIR[$i]:-}" ]]; then
      "$CLI" -testnet4 -datadir="${DATADIR[$i]}" -rpcport="${RPC[$i]}" stop >/dev/null 2>&1 || true
    fi
  done
  sleep 1
  for i in 1 2 3; do
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
  "$CLI" -testnet4 -datadir="${DATADIR[$id]}" -rpcport="${RPC[$id]}" "$@"
}

wait_rpc() {
  local id="$1"
  for _ in $(seq 1 120); do
    if cli "$id" getblockcount >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "${PID[$id]}" >/dev/null 2>&1; then
      echo "node $id exited during startup" >&2
      cat "${DATADIR[$id]}/node.log" >&2 || true
      return 1
    fi
    sleep 1
  done
  echo "node $id RPC did not become ready" >&2
  cat "${DATADIR[$id]}/node.log" >&2 || true
  return 1
}

start_node() {
  local id="$1"
  DATADIR[$id]="$ROOT/node$id"
  mkdir -p "${DATADIR[$id]}"
  "$DAEMON" \
    -testnet4 \
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
    -printtoconsole=0 \
    >"${DATADIR[$id]}/node.log" 2>&1 &
  PID[$id]=$!
  wait_rpc "$id"
}

wait_height() {
  local id="$1" expected="$2"
  for _ in $(seq 1 120); do
    if [[ "$(cli "$id" getblockcount 2>/dev/null || true)" == "$expected" ]]; then
      return 0
    fi
    sleep 1
  done
  echo "node $id did not reach height $expected (actual=$(cli "$id" getblockcount 2>/dev/null || echo unavailable))" >&2
  return 1
}

wait_same_tip() {
  local left="$1" right="$2"
  for _ in $(seq 1 120); do
    local lh rh
    lh="$(cli "$left" getbestblockhash 2>/dev/null || true)"
    rh="$(cli "$right" getbestblockhash 2>/dev/null || true)"
    if [[ -n "$lh" && "$lh" == "$rh" ]]; then
      return 0
    fi
    sleep 1
  done
  echo "nodes $left and $right failed to converge to the same tip" >&2
  return 1
}

mine() {
  local id="$1" blocks="$2"
  # raw(51) is an OP_TRUE descriptor. It avoids wallet dependencies and keeps
  # this test focused on node consensus/P2P/mining behavior.
  cli "$id" generatetodescriptor "$blocks" 'raw(51)' 5000000 >/dev/null
}

for i in 1 2 3; do
  start_node "$i"
done

echo "CRAK-009: three Crakbit testnet nodes started"

# Establish a shared chain on all three nodes.
cli 1 addnode "127.0.0.1:${P2P[2]}" onetry >/dev/null
cli 1 addnode "127.0.0.1:${P2P[3]}" onetry >/dev/null
mine 1 2
wait_height 2 2
wait_height 3 2
wait_same_tip 1 2
wait_same_tip 1 3
SHARED_TIP="$(cli 1 getbestblockhash)"
echo "CRAK-009: initial three-node sync height=2 tip=$SHARED_TIP"

# Partition node 1 from the other peers and mine competing branches.
cli 1 disconnectnode "127.0.0.1:${P2P[2]}" >/dev/null || true
cli 1 disconnectnode "127.0.0.1:${P2P[3]}" >/dev/null || true
sleep 1

mine 1 2   # height 4 branch A
mine 2 4   # height 6 branch B, more accumulated work at comparable targets
A_TIP="$(cli 1 getbestblockhash)"
B_TIP="$(cli 2 getbestblockhash)"
[[ "$A_TIP" != "$B_TIP" ]] || { echo "partition did not produce distinct tips" >&2; exit 1; }
[[ "$(cli 1 getblockcount)" == "4" ]] || { echo "node 1 fork height mismatch" >&2; exit 1; }
[[ "$(cli 2 getblockcount)" == "6" ]] || { echo "node 2 fork height mismatch" >&2; exit 1; }
echo "CRAK-009: competing forks created A=4 B=6"

# Invalid-block smoke: keep the valid yespower header but mutate the final byte
# of the serialized coinbase transaction. The block remains parseable while its
# transaction merkle root no longer matches the committed header.
RAW_BLOCK="$(cli 1 getblock "$A_TIP" 0)"
BAD_BLOCK="$(python3 - "$RAW_BLOCK" <<'PY'
import sys
raw = bytearray.fromhex(sys.argv[1])
if len(raw) <= 84:
    raise SystemExit("block unexpectedly short")
raw[-1] ^= 0x01
print(raw.hex())
PY
)"
INVALID_RESULT="$(cli 2 submitblock "$BAD_BLOCK" 2>/dev/null || true)"
if [[ -z "$INVALID_RESULT" || "$INVALID_RESULT" == "null" ]]; then
  echo "mutated block was unexpectedly accepted" >&2
  exit 1
fi
echo "CRAK-009: invalid block rejected result=$INVALID_RESULT"

# Reconnect node 1 to the longer branch and require an actual reorg.
cli 1 addnode "127.0.0.1:${P2P[2]}" onetry >/dev/null
wait_height 1 6
wait_same_tip 1 2
POST_REORG_TIP="$(cli 1 getbestblockhash)"
[[ "$POST_REORG_TIP" == "$B_TIP" ]] || { echo "node 1 did not reorganize to node 2 tip" >&2; exit 1; }
echo "CRAK-009: node 1 reorged to longer-work branch tip=$POST_REORG_TIP"

# Bring the third node onto the final chain as an independent synchronization gate.
cli 3 addnode "127.0.0.1:${P2P[2]}" onetry >/dev/null
wait_height 3 6
wait_same_tip 2 3
FINAL_TIP="$(cli 3 getbestblockhash)"

echo "CRAK-009 multi-node smoke: OK height=6 tip=$FINAL_TIP"
