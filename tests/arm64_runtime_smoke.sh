#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
TMP="$(mktemp -d)"
OUT="$TMP/out"
EXTRACT="$TMP/extract"
PREFIX="$TMP/prefix"
DATADIR="$TMP/datadir"
POOL_DB="$TMP/arm64-pool.sqlite3"
POOL_LOG="$TMP/pool.log"
WORKER_LOG="$TMP/worker.log"
POOL_PID=""
POOLPORT=19863

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

case "$(uname -m)" in
  aarch64|arm64) ;;
  *) echo "CRAK-023 requires a native ARM64 runner, got $(uname -m)" >&2; exit 1 ;;
esac

for cmd in file python3 sha256sum tar; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing required command: $cmd" >&2; exit 1; }
done
for bin in crakbitd crakbit-cli crakminer-scan; do
  [[ -x "$BUILD_DIR/bin/$bin" ]] || { echo "missing ARM64 build input: $BUILD_DIR/bin/$bin" >&2; exit 1; }
done

# Prove the binaries being packaged are native ARM64 ELF files, not emulated x64
# artifacts copied onto an ARM runner.
for bin in crakbitd crakbit-cli crakminer-scan; do
  INFO="$(file "$BUILD_DIR/bin/$bin")"
  printf '%s\n' "$INFO"
  grep -Eiq 'ELF 64-bit.*(ARM aarch64|aarch64)' <<<"$INFO" || {
    echo "CRAK-023 expected native ARM64 ELF for $bin" >&2
    exit 1
  }
done

mkdir -p "$OUT" "$EXTRACT"
CRAKBIT_VERSION=ci-arm64 bash "$ROOT/scripts/package-linux.sh" "$BUILD_DIR" "$OUT" >/dev/null
ARCHIVE="$(find "$OUT" -maxdepth 1 -type f -name 'crakbit-core-ci-arm64-linux-arm64.tar.gz' -print -quit)"
[[ -n "$ARCHIVE" ]] || { echo "CRAK-023 ARM64 package archive not produced" >&2; exit 1; }
(
  cd "$OUT"
  sha256sum -c "$(basename "$ARCHIVE").sha256"
)

tar -C "$EXTRACT" -xzf "$ARCHIVE"
PKGDIR="$(find "$EXTRACT" -mindepth 1 -maxdepth 1 -type d -name 'crakbit-core-ci-arm64-linux-arm64' -print -quit)"
[[ -n "$PKGDIR" ]] || { echo "CRAK-023 extracted ARM64 package directory not found" >&2; exit 1; }
(
  cd "$PKGDIR"
  sha256sum -c SHA256SUMS
)

python3 - "$PKGDIR/share/doc/crakbit-core/BUILD-MANIFEST.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding='utf-8'))
assert m['platform'] == 'linux', m
assert m['arch'] == 'arm64', m
assert m['mainnet_enabled'] is False, m
assert len(m['source_commit']) == 40, m
assert m['source_date_epoch'] > 0, m
PY

bash "$PKGDIR/install.sh" "$PREFIX" >/dev/null

for bin in \
  crakbitd crakbit-cli crakbit-start crakbit-mine crakminer crakminer-native \
  crakminer-scan crakpool crakpool-stats crakpool-payout crakpool-paytx \
  crakpool-payguard crakpool-payops crakminer-stratum; do
  [[ -x "$PREFIX/bin/$bin" ]] || { echo "CRAK-023 installed command missing: $bin" >&2; exit 1; }
done
[[ -f "$PREFIX/bin/crakpool-base.py" ]] || { echo "CRAK-023 crakpool-base.py missing" >&2; exit 1; }

# Re-check the installed native binaries, then execute the actual node, wallet,
# RPC miner and native yespower scanner on ARM64 hardware.
for bin in crakbitd crakbit-cli crakminer-scan; do
  file "$PREFIX/bin/$bin" | grep -Eiq 'ELF 64-bit.*(ARM aarch64|aarch64)' || {
    echo "CRAK-023 installed binary is not ARM64: $bin" >&2
    exit 1
  }
done

CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakbit-start" regtest -connect=0 >/dev/null
"$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" createwallet armci >/dev/null
CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakbit-mine" armci 1 regtest 1000000 >/dev/null

HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
[[ "$HEIGHT" == "1" ]] || { echo "CRAK-023 RPC miner expected height 1, got $HEIGHT" >&2; exit 1; }

CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakminer-native" \
  --network regtest \
  --wallet armci \
  --threads 1 \
  --cpu-limit 100 \
  --blocks 1 \
  --batch-hashes 64 >/dev/null

HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
[[ "$HEIGHT" == "2" ]] || { echo "CRAK-023 native miner expected height 2, got $HEIGHT" >&2; exit 1; }

# Exercise the installed persistent pool and Stratum worker natively on ARM64.
"$PREFIX/bin/crakpool" \
  --network regtest \
  --wallet armci \
  --listen 127.0.0.1 \
  --port "$POOLPORT" \
  --share-difficulty 0.000000001 \
  --datadir "$DATADIR" \
  --db "$POOL_DB" \
  --payout-mode proportional \
  --pool-fee-bps 0 \
  >"$POOL_LOG" 2>&1 &
POOL_PID=$!

for _ in $(seq 1 60); do
  if grep -Fq 'crakpool ready ' "$POOL_LOG" 2>/dev/null; then
    break
  fi
  if ! kill -0 "$POOL_PID" >/dev/null 2>&1; then
    echo "CRAK-023 ARM64 pool exited during startup" >&2
    cat "$POOL_LOG" >&2 || true
    exit 1
  fi
  sleep 1
done
grep -F 'crakpool ready ' "$POOL_LOG" >/dev/null

"$PREFIX/bin/crakminer-stratum" \
  --pool "127.0.0.1:$POOLPORT" \
  --worker arm64.worker \
  --threads 1 \
  --cpu-limit 100 \
  --batch-hashes 64 \
  --shares 1 \
  --blocks 1 \
  >"$WORKER_LOG" 2>&1

HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
[[ "$HEIGHT" == "3" ]] || {
  echo "CRAK-023 Stratum worker expected height 3, got $HEIGHT" >&2
  cat "$POOL_LOG" >&2 || true
  cat "$WORKER_LOG" >&2 || true
  exit 1
}

grep -F 'crakpool BLOCK worker=arm64.worker ' "$POOL_LOG" >/dev/null
grep -F 'crakminer-stratum complete accepted=1 blocks=1 ' "$WORKER_LOG" >/dev/null

"$PREFIX/bin/crakpool-stats" --db "$POOL_DB" --window 600 --json >"$TMP/stats.json"
python3 - "$TMP/stats.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding='utf-8'))
assert s['blocks'] == 1, s
assert s['reward_sats'] == 500_000_000, s
assert s['pending_sats'] == 500_000_000, s
assert s['workers'][0]['worker'] == 'arm64.worker', s
PY

kill "$POOL_PID" >/dev/null 2>&1 || true
wait "$POOL_PID" >/dev/null 2>&1 || true
POOL_PID=""

# Validate the installed payout/operations Python entry points load and operate
# against the real ARM64-created pool ledger without enabling signing/broadcast.
WORKER_ADDRESS="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" -rpcwallet=armci getnewaddress '' bech32)"
"$PREFIX/bin/crakpool-payout" --db "$POOL_DB" register \
  --network regtest \
  --datadir "$DATADIR" \
  --worker arm64.worker \
  --address "$WORKER_ADDRESS" >/dev/null
"$PREFIX/bin/crakpool-payout" --db "$POOL_DB" status >"$TMP/payout-status.json"
"$PREFIX/bin/crakpool-payops" --db "$POOL_DB" summary >"$TMP/payops-summary.json"
"$PREFIX/bin/crakpool-paytx" --help >/dev/null
"$PREFIX/bin/crakpool-payguard" --help >/dev/null

python3 - "$TMP/payout-status.json" "$TMP/payops-summary.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding='utf-8'))
o = json.load(open(sys.argv[2], encoding='utf-8'))
assert p['registered_workers'] == 1, p
assert p['credits']['pending']['sats'] == 500_000_000, p
assert o['batches'] == 0, o
PY

"$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" stop >/dev/null

echo "CRAK-023 ARM64 runtime smoke: OK arch=arm64 height=$HEIGHT package=$(basename "$ARCHIVE") node=ok wallet=ok native_miner=ok stratum=ok payout_tools=ok"
