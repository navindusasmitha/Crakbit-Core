#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILDER_ID="${1:-${CRAKBIT_REPRO_BUILDER_ID:-builder-local}}"
RUNNER_LABEL="${CRAKBIT_REPRO_RUNNER_LABEL:-local}"
BUILD_DIR="${CRAKBIT_REPRO_BUILD_DIR:-$ROOT/.work/crakbit-repro-build}"
OUT_DIR="${CRAKBIT_REPRO_OUT_DIR:-$ROOT/.work/crakbit-repro-out}"
BUNDLE_ROOT="${CRAKBIT_REPRO_BUNDLE_ROOT:-$ROOT/.work/repro-bundles}"
BUNDLE="$BUNDLE_ROOT/$BUILDER_ID"
VERSION="${CRAKBIT_REPRO_VERSION:-0.1.0-repro}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "CRAK-024 independent builder requires Linux" >&2
  exit 1
fi
if [[ "$(uname -m)" != "x86_64" && "$(uname -m)" != "amd64" ]]; then
  echo "CRAK-024 current cross-builder contract requires x86_64, got $(uname -m)" >&2
  exit 1
fi
if [[ ! "$BUILDER_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "invalid builder id: $BUILDER_ID" >&2
  exit 1
fi

for cmd in git cmake cc c++ python3 sha256sum tar gzip file; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing required command: $cmd" >&2; exit 1; }
done

# GitHub job containers mount the checkout with host ownership. actions/checkout
# temporarily marks it safe while the action runs, but later shell steps may use a
# different HOME. Explicitly trust only this exact checked-out repository path so
# source-commit/epoch discovery remains fail-closed instead of using unsafe '*'.
git config --global --add safe.directory "$ROOT"

[[ -d "$ROOT/.work/crakbit" ]] || {
  echo "materialized source missing; run scripts/bootstrap.sh and scripts/materialize-locked.sh first" >&2
  exit 1
}

SOURCE_COMMIT="${CRAKBIT_SOURCE_COMMIT:-$(git -C "$ROOT" rev-parse HEAD)}"
if [[ ! "$SOURCE_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "invalid source commit: $SOURCE_COMMIT" >&2
  exit 1
fi
SOURCE_COMMIT="${SOURCE_COMMIT,,}"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "$ROOT" show -s --format=%ct "$SOURCE_COMMIT")}" 
if [[ ! "$SOURCE_DATE_EPOCH" =~ ^[0-9]+$ ]]; then
  echo "invalid SOURCE_DATE_EPOCH: $SOURCE_DATE_EPOCH" >&2
  exit 1
fi

# Keep compiler output independent from the checkout's absolute path. The
# materialized Bitcoin/Crakbit tree already adds a source-level macro map; CRAK-024
# expands normalization to all files/debug info rooted in this checkout.
REPRO_PREFIX_FLAGS="-ffile-prefix-map=$ROOT=. -fdebug-prefix-map=$ROOT=. -fmacro-prefix-map=$ROOT=."
export CFLAGS="${CFLAGS:-} $REPRO_PREFIX_FLAGS"
export CXXFLAGS="${CXXFLAGS:-} $REPRO_PREFIX_FLAGS"
export SOURCE_DATE_EPOCH
export LC_ALL=C
export LANG=C
export TZ=UTC

rm -rf "$BUILD_DIR" "$OUT_DIR" "$BUNDLE"
mkdir -p "$BUILD_DIR" "$OUT_DIR" "$BUNDLE"

cmake -S "$ROOT/.work/crakbit" -B "$BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DENABLE_WALLET=ON \
  -DENABLE_EXTERNAL_SIGNER=OFF \
  -DENABLE_IPC=OFF \
  -DWITH_ZMQ=OFF \
  -DWITH_EMBEDDED_ASMAP=OFF \
  -DBUILD_GUI=OFF \
  -DBUILD_TESTS=OFF \
  -DBUILD_BENCH=OFF \
  -DBUILD_DAEMON=ON \
  -DBUILD_CLI=ON \
  -DBUILD_TX=OFF \
  -DBUILD_UTIL=OFF \
  -DBUILD_BITCOIN_BIN=OFF

cmake --build "$BUILD_DIR" --target bitcoind bitcoin-cli --parallel "${CRAKBIT_REPRO_JOBS:-2}"
bash "$ROOT/scripts/build-native-miner.sh" "$BUILD_DIR/bin/crakminer-scan"

for bin in crakbitd crakbit-cli crakminer-scan; do
  test -x "$BUILD_DIR/bin/$bin"
  file "$BUILD_DIR/bin/$bin" | grep -Eq 'ELF 64-bit.*x86-64|ELF 64-bit.*x86_64'
done

CRAKBIT_VERSION="$VERSION" \
CRAKBIT_SOURCE_COMMIT="$SOURCE_COMMIT" \
SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
  bash "$ROOT/scripts/package-linux.sh" "$BUILD_DIR" "$OUT_DIR" >/tmp/crakbit-repro-package-paths.txt

ARCHIVE="$OUT_DIR/crakbit-core-${VERSION}-linux-x86_64.tar.gz"
SIDECAR="$ARCHIVE.sha256"
test -f "$ARCHIVE"
test -f "$SIDECAR"
cp "$ARCHIVE" "$SIDECAR" "$BUNDLE/"

# repro-manifest.py opens the final package and hashes the release binaries
# directly from the archive. This avoids uploading a second copy of large debug
# binaries while still proving their byte identity independently from the tarball
# hash itself.
python3 "$ROOT/scripts/repro-manifest.py" create \
  --bundle "$BUNDLE" \
  --builder-id "$BUILDER_ID" \
  --runner-label "$RUNNER_LABEL" \
  --source-commit "$SOURCE_COMMIT" \
  --source-date-epoch "$SOURCE_DATE_EPOCH"

printf 'CRAK-024 independent builder complete: %s\n' "$BUILDER_ID"
printf 'bundle=%s\n' "$BUNDLE"
printf 'source_commit=%s\n' "$SOURCE_COMMIT"
printf 'source_date_epoch=%s\n' "$SOURCE_DATE_EPOCH"
