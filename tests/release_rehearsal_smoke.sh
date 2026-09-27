#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-interop-build}"
EXPECTED_ARCH="${2:-}"
TMP="$(mktemp -d)"
OUT_A="$TMP/out-a"
OUT_B="$TMP/out-b"
EXTRACT_A="$TMP/extract-a"
EXTRACT_B="$TMP/extract-b"
PREFIX="$TMP/prefix"
DATADIR="$TMP/datadir"
POOL_DB="$TMP/pool.sqlite3"
POOL_LOG="$TMP/pool.log"
WORKER_LOG="$TMP/worker.log"
POOL_PID=""
POOLPORT=19869
WALLET=rehearsal

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
  x86_64|amd64) NATIVE_ARCH=x86_64 ;;
  aarch64|arm64) NATIVE_ARCH=arm64 ;;
  *) echo "CRAK-029 unsupported native architecture: $(uname -m)" >&2; exit 1 ;;
esac
if [[ -z "$EXPECTED_ARCH" ]]; then
  EXPECTED_ARCH="$NATIVE_ARCH"
fi
[[ "$NATIVE_ARCH" == "$EXPECTED_ARCH" ]] || {
  echo "CRAK-029 native runner mismatch: expected=$EXPECTED_ARCH actual=$NATIVE_ARCH" >&2
  exit 1
}

for cmd in file git python3 sha256sum tar; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing required command: $cmd" >&2; exit 1; }
done
for bin in crakbitd crakbit-cli crakminer-scan; do
  [[ -x "$BUILD_DIR/bin/$bin" ]] || { echo "missing rehearsal build input: $BUILD_DIR/bin/$bin" >&2; exit 1; }
done
[[ -f "$ROOT/release/INTEROP_MATRIX.json" ]] || { echo "missing release/INTEROP_MATRIX.json" >&2; exit 1; }

SOURCE_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
SOURCE_EPOCH="$(git -C "$ROOT" show -s --format=%ct "$SOURCE_COMMIT")"
export CRAKBIT_SOURCE_COMMIT="$SOURCE_COMMIT"
export SOURCE_DATE_EPOCH="$SOURCE_EPOCH"

check_native_binary() {
  local path="$1"
  local info
  info="$(file "$path")"
  printf '%s\n' "$info"
  case "$EXPECTED_ARCH" in
    x86_64) grep -Eiq 'ELF 64-bit.*(x86-64|x86_64)' <<<"$info" ;;
    arm64) grep -Eiq 'ELF 64-bit.*(ARM aarch64|aarch64)' <<<"$info" ;;
  esac || { echo "CRAK-029 wrong native binary architecture: $path" >&2; exit 1; }
}

for bin in crakbitd crakbit-cli crakminer-scan; do
  check_native_binary "$BUILD_DIR/bin/$bin"
done

package_and_extract() {
  local version="$1"
  local out="$2"
  local extract="$3"
  mkdir -p "$out" "$extract"
  CRAKBIT_VERSION="$version" bash "$ROOT/scripts/package-linux.sh" "$BUILD_DIR" "$out" >/dev/null
  local archive
  archive="$(find "$out" -maxdepth 1 -type f -name "crakbit-core-${version}-linux-${EXPECTED_ARCH}.tar.gz" -print -quit)"
  [[ -n "$archive" ]] || { echo "CRAK-029 package missing for version=$version arch=$EXPECTED_ARCH" >&2; exit 1; }
  (
    cd "$out"
    sha256sum -c "$(basename "$archive").sha256"
  )
  tar -C "$extract" -xzf "$archive"
  local pkgdir="$extract/crakbit-core-${version}-linux-${EXPECTED_ARCH}"
  [[ -d "$pkgdir" ]] || { echo "CRAK-029 extracted package missing: $pkgdir" >&2; exit 1; }
  (
    cd "$pkgdir"
    sha256sum -c SHA256SUMS
  )
  python3 - "$pkgdir/share/doc/crakbit-core/BUILD-MANIFEST.json" "$version" "$EXPECTED_ARCH" "$SOURCE_COMMIT" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
assert m["package_version"] == sys.argv[2], m
assert m["arch"] == sys.argv[3], m
assert m["source_commit"] == sys.argv[4], m
assert m["platform"] == "linux", m
assert m["mainnet_enabled"] is False, m
PY
  printf '%s\n' "$archive" "$pkgdir"
}

mapfile -t A_PATHS < <(package_and_extract ci-rehearsal-a "$OUT_A" "$EXTRACT_A")
ARCHIVE_A="${A_PATHS[-2]}"
PKG_A="${A_PATHS[-1]}"
bash "$PKG_A/install.sh" "$PREFIX" >/dev/null

for command in \
  crakbitd crakbit-cli crakbit-start crakbit-mine crakminer-scan crakminer-native \
  crakminer-stratum crakpool crakpool-stats crakpool-edge; do
  [[ -x "$PREFIX/bin/$command" ]] || { echo "CRAK-029 installed command missing: $command" >&2; exit 1; }
done
for bin in crakbitd crakbit-cli crakminer-scan; do
  check_native_binary "$PREFIX/bin/$bin"
done

CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakbit-start" regtest -connect=0 >/dev/null
"$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" createwallet "$WALLET" >/dev/null
CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakbit-mine" "$WALLET" 1 regtest 1000000 >/dev/null
CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakminer-native" \
  --network regtest --wallet "$WALLET" --threads 1 --cpu-limit 100 --blocks 1 --batch-hashes 64 >/dev/null

HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
[[ "$HEIGHT" == 2 ]] || { echo "CRAK-029 expected pre-Stratum height 2, got $HEIGHT" >&2; exit 1; }

"$PREFIX/bin/crakpool" \
  --network regtest --wallet "$WALLET" --listen 127.0.0.1 --port "$POOLPORT" \
  --share-difficulty 0.000000001 --datadir "$DATADIR" --db "$POOL_DB" \
  --payout-mode proportional --pool-fee-bps 0 >"$POOL_LOG" 2>&1 &
POOL_PID=$!
for _ in $(seq 1 60); do
  if grep -Fq 'crakpool ready ' "$POOL_LOG" 2>/dev/null; then break; fi
  if ! kill -0 "$POOL_PID" >/dev/null 2>&1; then
    echo "CRAK-029 pool exited during startup" >&2
    cat "$POOL_LOG" >&2 || true
    exit 1
  fi
  sleep 1
done
grep -F 'crakpool ready ' "$POOL_LOG" >/dev/null

python3 "$ROOT/tests/interop_protocol_probe.py" --port "$POOLPORT" --worker independent.probe

"$PREFIX/bin/crakminer-stratum" \
  --pool "127.0.0.1:$POOLPORT" --worker rehearsal.worker --threads 1 --cpu-limit 100 \
  --batch-hashes 64 --shares 1 --blocks 1 >"$WORKER_LOG" 2>&1

grep -F 'crakminer-stratum complete accepted=1 blocks=1 ' "$WORKER_LOG" >/dev/null
HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
[[ "$HEIGHT" == 3 ]] || { echo "CRAK-029 Stratum interoperability expected height 3, got $HEIGHT" >&2; exit 1; }

"$PREFIX/bin/crakpool-stats" --db "$POOL_DB" --window 600 --json >"$TMP/stats-before.json"
python3 - "$TMP/stats-before.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1], encoding="utf-8"))
assert s["blocks"] == 1, s
assert s["reward_sats"] == 500_000_000, s
assert s["pending_sats"] == 500_000_000, s
PY

PRE_UPGRADE_HEIGHT="$HEIGHT"
PRE_UPGRADE_TIP="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getbestblockhash)"
PRE_UPGRADE_WALLET_ADDR="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" -rpcwallet="$WALLET" getnewaddress '' bech32)"

kill "$POOL_PID" >/dev/null 2>&1 || true
wait "$POOL_PID" >/dev/null 2>&1 || true
POOL_PID=""
"$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" stop >/dev/null

mapfile -t B_PATHS < <(package_and_extract ci-rehearsal-b "$OUT_B" "$EXTRACT_B")
ARCHIVE_B="${B_PATHS[-2]}"
PKG_B="${B_PATHS[-1]}"
bash "$PKG_B/install.sh" "$PREFIX" >/dev/null

python3 "$ROOT/scripts/release-trust.py" manifest \
  --archive "$ARCHIVE_B" --policy "$ROOT/release/RELEASE_POLICY.json" \
  --source-commit "$SOURCE_COMMIT" --channel testnet --output "$OUT_B/RELEASE-MANIFEST.json"
python3 "$ROOT/scripts/release-trust.py" verify \
  --manifest "$OUT_B/RELEASE-MANIFEST.json" --bundle "$OUT_B"

CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakbit-start" regtest -connect=0 >/dev/null
LOADED="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" listwallets)"
if ! python3 - "$WALLET" "$LOADED" <<'PY'
import json, sys
raise SystemExit(0 if sys.argv[1] in json.loads(sys.argv[2]) else 1)
PY
then
  "$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" loadwallet "$WALLET" >/dev/null
fi

POST_UPGRADE_HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
POST_UPGRADE_TIP="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getbestblockhash)"
[[ "$POST_UPGRADE_HEIGHT" == "$PRE_UPGRADE_HEIGHT" ]] || {
  echo "CRAK-029 upgrade did not preserve chain height" >&2
  exit 1
}
[[ "$POST_UPGRADE_TIP" == "$PRE_UPGRADE_TIP" ]] || {
  echo "CRAK-029 upgrade preserved chain height but changed tip" >&2
  exit 1
}
"$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" -rpcwallet="$WALLET" getaddressinfo "$PRE_UPGRADE_WALLET_ADDR" >"$TMP/address-after.json"
python3 - "$TMP/address-after.json" <<'PY'
import json, sys
info = json.load(open(sys.argv[1], encoding="utf-8"))
assert info.get("ismine") is True, info
PY
printf '%s\n' "CRAK-029 upgrade preserved chain tip: $POST_UPGRADE_TIP"

"$PREFIX/bin/crakpool-stats" --db "$POOL_DB" --window 600 --json >"$TMP/stats-after.json"
python3 - "$TMP/stats-before.json" "$TMP/stats-after.json" <<'PY'
import json, sys
before = json.load(open(sys.argv[1], encoding="utf-8"))
after = json.load(open(sys.argv[2], encoding="utf-8"))
for key in ("blocks", "reward_sats", "pending_sats"):
    assert after[key] == before[key], (key, before, after)
PY

CRAKBIT_DATADIR="$DATADIR" "$PREFIX/bin/crakminer-native" \
  --network regtest --wallet "$WALLET" --threads 1 --cpu-limit 100 --blocks 1 --batch-hashes 64 >/dev/null
FINAL_HEIGHT="$("$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" getblockcount)"
[[ "$FINAL_HEIGHT" == 4 ]] || { echo "CRAK-029 post-upgrade native mining expected height 4, got $FINAL_HEIGHT" >&2; exit 1; }

"$PREFIX/bin/crakpool-edge" --help >/dev/null
"$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" stop >/dev/null

echo "CRAK-029 release rehearsal: OK arch=$EXPECTED_ARCH package_a=$(basename "$ARCHIVE_A") package_b=$(basename "$ARCHIVE_B") height=$FINAL_HEIGHT gbt=ok independent_stratum=ok official_stratum=ok upgrade=ok wallet=ok ledger=ok trust_manifest=ok"
