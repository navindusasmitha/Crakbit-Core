#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
TMP="$(mktemp -d)"
OUT="$TMP/out"
EXTRACT="$TMP/extract"
PREFIX="$TMP/prefix"
DATADIR="$TMP/datadir"
POOL_DB="$TMP/package-pool.sqlite3"
POOL_PID=""
POOLPORT=19653

cleanup() {
  set +e
  if [[ -n "$POOL_PID" ]]; then
    kill "$POOL_PID" >/dev/null 2>&1 || true
    wait "$POOL_PID" >/dev/null 2>&1 || true
  fi
  if [[ -x "$PREFIX/bin/crakbit-cli" ]]; then
    "$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" stop >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

mkdir -p "$OUT" "$EXTRACT"
CRAKBIT_VERSION=ci bash "$ROOT/scripts/package-linux.sh" "$BUILD_DIR" "$OUT" >/dev/null

ARCHIVE="$(find "$OUT" -maxdepth 1 -type f -name 'crakbit-core-ci-linux-*.tar.gz' -print -quit)"
if [[ -z "$ARCHIVE" ]]; then
  echo "CRAK-011: package archive not produced" >&2
  exit 1
fi

(
  cd "$OUT"
  sha256sum -c "$(basename "$ARCHIVE").sha256"
)

tar -C "$EXTRACT" -xzf "$ARCHIVE"
PKGDIR="$(find "$EXTRACT" -mindepth 1 -maxdepth 1 -type d -name 'crakbit-core-ci-linux-*' -print -quit)"
if [[ -z "$PKGDIR" ]]; then
  echo "CRAK-011: extracted package directory not found" >&2
  exit 1
fi

(
  cd "$PKGDIR"
  sha256sum -c SHA256SUMS
)

bash "$PKGDIR/install.sh" "$PREFIX" >/dev/null

for bin in crakbitd crakbit-cli crakbit-start crakbit-mine crakminer crakminer-native crakminer-scan crakpool crakpool-stats crakpool-payout crakpool-pay crakminer-stratum; do
  test -x "$PREFIX/bin/$bin"
done
test -f "$PREFIX/bin/crakpool-base.py"

# Mainnet is intentionally disabled. Validate packaged binaries by exercising
# the allowed regtest network end-to-end instead of invoking them without a
# network selector and accidentally tripping the mainnet launch gate.
CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakbit-start" regtest -connect=0 >/dev/null
"$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" createwallet ciwallet >/dev/null
CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakbit-mine" ciwallet 1 regtest 1000000 >/dev/null

HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
if [[ "$HEIGHT" != "1" ]]; then
  echo "CRAK-011: packaged mining helper expected height 1, got $HEIGHT" >&2
  exit 1
fi

echo "CRAK-011 package smoke: OK archive=$(basename "$ARCHIVE") height=$HEIGHT"

CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakminer" \
  --network regtest \
  --wallet ciwallet \
  --threads 2 \
  --cpu-limit 50 \
  --blocks 2 \
  --maxtries 10000 >/dev/null

HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
if [[ "$HEIGHT" != "3" ]]; then
  echo "CRAK-012: controlled miner expected active height 3, got $HEIGHT" >&2
  exit 1
fi

echo "CRAK-012 controlled CPU miner smoke: OK height=$HEIGHT"

CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakminer-native" \
  --network regtest \
  --wallet ciwallet \
  --threads 2 \
  --cpu-limit 50 \
  --blocks 1 \
  --batch-hashes 64 >/dev/null

HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
if [[ "$HEIGHT" != "4" ]]; then
  echo "CRAK-013: native packaged miner expected active height 4, got $HEIGHT" >&2
  exit 1
fi

echo "CRAK-013 packaged native miner smoke: OK height=$HEIGHT"

# CRAK-015's public `crakpool` command wraps the CRAK-014 protocol engine with a
# persistent SQLite ledger. In this deterministic regtest path each accepted
# share is also a network block, so one block must create exactly 5 CRAK of
# pending accounting credit.
"$PREFIX/bin/crakpool" \
  --network regtest \
  --wallet ciwallet \
  --listen 127.0.0.1 \
  --port "$POOLPORT" \
  --share-difficulty 0.000000001 \
  --datadir "$DATADIR" \
  --db "$POOL_DB" \
  --payout-mode proportional \
  --pool-fee-bps 0 \
  >"$TMP/package-pool.log" 2>&1 &
POOL_PID=$!

for _ in $(seq 1 60); do
  if grep -Fq 'crakpool ready ' "$TMP/package-pool.log" 2>/dev/null; then
    break
  fi
  if ! kill -0 "$POOL_PID" >/dev/null 2>&1; then
    echo "CRAK-015: packaged pool exited during startup" >&2
    cat "$TMP/package-pool.log" >&2 || true
    exit 1
  fi
  sleep 1
done

grep -F 'crakpool ready ' "$TMP/package-pool.log" >/dev/null

"$PREFIX/bin/crakminer-stratum" \
  --pool "127.0.0.1:$POOLPORT" \
  --worker package.worker \
  --threads 2 \
  --cpu-limit 50 \
  --batch-hashes 64 \
  --shares 1 \
  --blocks 1 \
  >"$TMP/package-worker.log" 2>&1

HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
if [[ "$HEIGHT" != "5" ]]; then
  echo "CRAK-015: packaged Stratum miner expected active height 5, got $HEIGHT" >&2
  cat "$TMP/package-pool.log" >&2 || true
  cat "$TMP/package-worker.log" >&2 || true
  exit 1
fi

grep -F 'crakpool BLOCK worker=package.worker ' "$TMP/package-pool.log" >/dev/null
grep -F 'payout_mode=proportional' "$TMP/package-pool.log" >/dev/null
grep -F 'crakminer-stratum complete accepted=1 blocks=1 ' "$TMP/package-worker.log" >/dev/null

"$PREFIX/bin/crakpool-stats" --db "$POOL_DB" --window 600 --json >"$TMP/package-stats.json"
python3 - "$TMP/package-stats.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
assert s["blocks"] == 1, s
assert s["reward_sats"] == 500_000_000, s
assert s["pending_sats"] == 500_000_000, s
assert len(s["workers"]) == 1, s
w = s["workers"][0]
assert w["worker"] == "package.worker", w
assert w["accepted_shares"] == 1, w
assert w["pending_sats"] == 500_000_000, w
PY

kill "$POOL_PID" >/dev/null 2>&1 || true
wait "$POOL_PID" >/dev/null 2>&1 || true
POOL_PID=""

# CRAK-016 must be usable from the installed package, validate a real regtest
# address through the packaged node, and migrate the CRAK-015 ledger without
# enabling transaction broadcast.
WORKER_ADDRESS="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" -rpcwallet=ciwallet getnewaddress '' bech32)"
"$PREFIX/bin/crakpool-payout" --db "$POOL_DB" register \
  --network regtest \
  --datadir "$DATADIR" \
  --worker package.worker \
  --address "$WORKER_ADDRESS" \
  >"$TMP/package-register.json"
"$PREFIX/bin/crakpool-payout" --db "$POOL_DB" status >"$TMP/package-payout-status.json"
python3 - "$TMP/package-register.json" "$TMP/package-payout-status.json" <<'PY'
import json, sys
registered = json.load(open(sys.argv[1], encoding="utf-8"))
status = json.load(open(sys.argv[2], encoding="utf-8"))
assert registered["registered"] is True, registered
assert registered["worker"] == "package.worker", registered
assert status["registered_workers"] == 1, status
assert status["credits"]["pending"]["sats"] == 500_000_000, status
PY

# CRAK-017 package gate: opening status must create/read its payment schema
# without preparing, signing, or broadcasting any transaction.
"$PREFIX/bin/crakpool-pay" --db "$POOL_DB" status >"$TMP/package-payment-status.json"
python3 - "$TMP/package-payment-status.json" <<'PY'
import json, sys
status = json.load(open(sys.argv[1], encoding="utf-8"))
assert status["registered_workers"] == 1, status
assert status["credits"]["pending"]["sats"] == 500_000_000, status
assert status["transactions"] == {}, status
PY

"$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" stop >/dev/null
sleep 1

echo "CRAK-015/016/017 packaged pool smoke: OK height=$HEIGHT pending_sats=500000000 payout_and_payment_tools=installed"
