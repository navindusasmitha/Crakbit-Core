#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${CRAKBIT_REFERENCE_TREE:-$ROOT/build/reference}"
CORE="$REF/build/wam-core"
RANDOMX="$REF/build/randomx"
DIST="$ROOT/build/dist"
JOBS="${CRAKBIT_JOBS:-2}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ -d "$CORE/src" ] || die "materialized source not found; run scripts/materialize.sh first"
[ -f "$RANDOMX/build/librandomx.a" ] || die "RandomX static library missing"

cd "$CORE"
log "configure Crakbit testnet node"
[ -f ./configure ] || ./autogen.sh >/dev/null
./configure \
    --without-gui \
    --disable-zmq \
    --disable-tests-fuzz-binary \
    --with-incompatible-bdb \
    CPPFLAGS="-I$RANDOMX/src" \
    LIBS="$RANDOMX/build/librandomx.a -lpthread" \
    >/dev/null

log "compile node with $JOBS jobs"
make -j"$JOBS"

mkdir -p "$DIST"
copy_bin() {
    local from="$1" to="$2"
    if [ -x "$from" ]; then
        cp "$from" "$DIST/$to"
        chmod +x "$DIST/$to"
    fi
}

# The pinned compatibility layer still produces WAM-named internals. Testnet
# artifacts are exposed under Crakbit names. Full internal renaming is a
# pre-mainnet code-freeze task so it cannot destabilize consensus work now.
copy_bin src/wamd crakbitd-bin
copy_bin src/wam-cli crakbit-cli-bin
copy_bin src/wam-tx crakbit-tx
copy_bin src/wam-util crakbit-util
copy_bin src/wam-wallet crakbit-wallet

[ -x "$DIST/crakbitd-bin" ] || die "node binary was not produced"
[ -x "$DIST/crakbit-cli-bin" ] || die "CLI binary was not produced"

# Testnet package wrappers deliberately force -testnet. A user can still inspect
# the raw *-bin executable, but the documented artifact cannot accidentally be
# started on the unfinished mainnet parameter set.
cat > "$DIST/crakbitd" <<'EOF'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/crakbitd-bin" -testnet "$@"
EOF
cat > "$DIST/crakbit-cli" <<'EOF'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/crakbit-cli-bin" -testnet "$@"
EOF
chmod +x "$DIST/crakbitd" "$DIST/crakbit-cli"

log "build Crakbit CPU miner"
RANDOMX_INCLUDE="$RANDOMX/src" \
RANDOMX_LIB="$RANDOMX/build/librandomx.a" \
OUT="$DIST/crakbit-miner" \
CXXFLAGS="${CRAKBIT_MINER_CXXFLAGS:--O3 -mtune=generic}" \
bash "$REF/miner/build.sh"

[ -x "$DIST/crakbit-miner" ] || die "miner binary was not produced"

log "binary self-check on testnet"
"$DIST/crakbitd" -version | head -n 6
"$DIST/crakbit-miner" --self-test --no-colour

sha256sum "$DIST"/crakbit* > "$DIST/SHA256SUMS"
log "artifacts: $DIST"
