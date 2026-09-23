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

log "compile with $JOBS jobs"
make -j"$JOBS"

mkdir -p "$DIST"
copy_bin() {
    local from="$1" to="$2"
    if [ -x "$from" ]; then
        cp "$from" "$DIST/$to"
        chmod +x "$DIST/$to"
    fi
}

# The pinned compatibility layer builds WAM-named internals. Testnet artifacts
# are exposed under Crakbit names; the internal rename is deferred until the
# behavior is stable and is a mainnet gate.
copy_bin src/wamd crakbitd
copy_bin src/wam-cli crakbit-cli
copy_bin src/wam-tx crakbit-tx
copy_bin src/wam-util crakbit-util
copy_bin src/wam-wallet crakbit-wallet

[ -x "$DIST/crakbitd" ] || die "node binary was not produced"
[ -x "$DIST/crakbit-cli" ] || die "CLI binary was not produced"

log "binary self-check on testnet"
"$DIST/crakbitd" -testnet -version | head -n 6

sha256sum "$DIST"/crakbit* > "$DIST/SHA256SUMS"
log "artifacts: $DIST"
