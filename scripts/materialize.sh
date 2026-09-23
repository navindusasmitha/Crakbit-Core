#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/build/reference}"
ARTIFACTS="${CRAKBIT_ARTIFACTS:-$ROOT/build/artifacts}"
WAM_REPO="https://github.com/wam-coin-official/wam-coin.git"
WAM_COMMIT="e65bc4d5767e76182bf7bc712a91a8532459498d"
TESTNET_BURN="T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb"
MAINNET_BURN="WNg2svm2qApxheBKndKGQ9sRwporvRgRpT"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null || die "git is required"
command -v python3 >/dev/null || die "python3 is required"
command -v cmake >/dev/null || die "cmake is required"

if [ -e "$OUT" ]; then
    die "$OUT already exists; remove it explicitly before rematerializing"
fi
mkdir -p "$(dirname "$OUT")" "$ARTIFACTS"

log "clone pinned WAM reference"
git clone --quiet "$WAM_REPO" "$OUT"
git -C "$OUT" checkout --quiet "$WAM_COMMIT"
ACTUAL="$(git -C "$OUT" rev-parse HEAD)"
[ "$ACTUAL" = "$WAM_COMMIT" ] || die "reference commit mismatch: $ACTUAL"

log "apply Crakbit testnet overlay"
python3 "$ROOT/scripts/crakbitize.py" --tree "$OUT" --overlay "$ROOT/overlay"
python3 "$ROOT/scripts/patch-miner-addresses.py" --tree "$OUT"
python3 "$ROOT/scripts/patch-pool-tests.py" --tree "$OUT"

log "materialize pinned Bitcoin Core + RandomX build trees"
bash "$OUT/scripts/fetch-upstream.sh"

# genesis/randomx_ffi.py needs a shared library. The node uses the static
# library produced above; this second build is only for deterministic genesis
# generation and uses the same pinned RandomX source checkout.
RANDOMX_DIR="$OUT/build/randomx"
FFI_BUILD="$RANDOMX_DIR/build-shared"
log "build shared RandomX library for the genesis generator"
cmake -S "$RANDOMX_DIR" -B "$FFI_BUILD" \
      -DCMAKE_BUILD_TYPE=Release -DARCH=x86-64 -DBUILD_SHARED_LIBS=ON >/dev/null
cmake --build "$FFI_BUILD" -j"${CRAKBIT_JOBS:-2}" >/dev/null

LIB=""
for candidate in \
    "$FFI_BUILD/librandomx.so" \
    "$FFI_BUILD/src/librandomx.so" \
    "$FFI_BUILD/librandomx.dylib"; do
    if [ -f "$candidate" ]; then LIB="$candidate"; break; fi
done
[ -n "$LIB" ] || die "shared librandomx was not produced in $FFI_BUILD"
export WAM_LIBRANDOMX="$LIB"

log "mine/freeze Crakbit testnet genesis"
python3 "$OUT/genesis/genesis_generator.py" \
    --network testnet \
    --address "$TESTNET_BURN" \
    --threads "${CRAKBIT_GENESIS_THREADS:-2}" \
    --json "$ARTIFACTS/testnet-genesis.json" \
    --patch "$OUT/src/wam/chainparams.cpp"

# Core constructs CMainParams while preparing command-line help even for a
# testnet invocation. The testnet branch therefore carries a construction-only
# placeholder main genesis, with no peers and no supported packaging path. It
# deliberately uses the same time/target/domain as testnet and is replaced by a
# completely independent genesis in the future mainnet code-freeze commit.
log "mine/freeze construction-only placeholder main genesis"
python3 "$OUT/genesis/genesis_generator.py" \
    --network mainnet \
    --address "$MAINNET_BURN" \
    --threads "${CRAKBIT_GENESIS_THREADS:-2}" \
    --json "$ARTIFACTS/placeholder-main-genesis.json" \
    --patch "$OUT/src/wam/chainparams.cpp" \
    --quiet

log "mine/freeze Crakbit regtest genesis"
python3 "$OUT/genesis/genesis_generator.py" \
    --network regtest \
    --address "$TESTNET_BURN" \
    --threads "${CRAKBIT_GENESIS_THREADS:-2}" \
    --json "$ARTIFACTS/regtest-genesis.json" \
    --patch "$OUT/src/wam/chainparams.cpp" \
    --quiet

# fetch-upstream copied chainparams before genesis was mined. Replace that one
# generated file with the now-frozen copy; every other consensus integration
# remains the pinned reference patch layer.
cp "$OUT/src/wam/chainparams.cpp" "$OUT/build/wam-core/src/kernel/chainparams.cpp"

cat > "$ARTIFACTS/materialized-source.txt" <<EOF
crakbit_branch=testnet-v0.1
wam_reference_commit=$WAM_COMMIT
materialized_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
core_tree=$OUT/build/wam-core
randomx_tree=$OUT/build/randomx
EOF

log "complete source tree: $OUT/build/wam-core"
log "testnet genesis:     $ARTIFACTS/testnet-genesis.json"
log "regtest genesis:     $ARTIFACTS/regtest-genesis.json"
