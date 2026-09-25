#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"
CORE_DIR="$BUILD_DIR/wam-core"
YESPOWER_DIR="$BUILD_DIR/yespower"
YESPOWER_REPO="https://github.com/openwall/yespower.git"
YESPOWER_COMMIT="1977c283bc43eed5a2c2579e02d6d996e49866b0"

log() { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

for cmd in git python3 cc ar cmake; do
    command -v "$cmd" >/dev/null 2>&1 || die "missing required command: $cmd"
done

# 1) Let WAM's audited v0.1.9 patch framework materialize its pinned Bitcoin
# Core v28.1 base. Our overlay files in src/wam already contain the Crakbit
# economic schedule and yespower compatibility implementation.
log "materializing WAM-derived Bitcoin Core v28.1 tree"
bash "$ROOT/scripts/fetch-upstream.sh"

# 2) Fetch yespower by immutable commit, never by a moving branch/tag.
log "fetching Openwall yespower $YESPOWER_COMMIT"
if [[ ! -d "$YESPOWER_DIR/.git" ]]; then
    git clone --quiet "$YESPOWER_REPO" "$YESPOWER_DIR"
fi
git -C "$YESPOWER_DIR" fetch --quiet origin "$YESPOWER_COMMIT"
git -C "$YESPOWER_DIR" checkout --quiet --detach "$YESPOWER_COMMIT"
[[ "$(git -C "$YESPOWER_DIR" rev-parse HEAD)" == "$YESPOWER_COMMIT" ]] \
    || die "yespower source lock mismatch"

# 3) Build only the official library objects used by yespower's own Makefile.
# Do not use -march=native for a binary that will be distributed to weaker CPUs.
log "building portable libyespower.a"
rm -f "$YESPOWER_DIR/yespower-opt.o" "$YESPOWER_DIR/sha256.o" "$YESPOWER_DIR/libyespower.a"
(
    cd "$YESPOWER_DIR"
    cc -c -O2 -fomit-frame-pointer -fPIC -I. yespower-opt.c -o yespower-opt.o
    cc -c -O2 -fomit-frame-pointer -fPIC -I. sha256.c -o sha256.o
    ar rcs libyespower.a yespower-opt.o sha256.o
)
[[ -s "$YESPOWER_DIR/libyespower.a" ]] || die "libyespower.a was not produced"

# 4) Convert the WAM-generated tree into an isolated Crakbit testnet tree.
log "applying Crakbit migration transform"
python3 "$ROOT/scripts/crakbitize.py" --tree "$CORE_DIR"

cat > "$CORE_DIR/.crakbit-source-lock" <<EOF
wam=v0.1.9@9c58108d3b021eaacdcf6bc92eb76cf720f31b6d
bitcoin=v28.1
yespower=$YESPOWER_COMMIT
EOF

log "Crakbit source tree ready"
log "  core:     $CORE_DIR"
log "  yespower: $YESPOWER_DIR/libyespower.a"
