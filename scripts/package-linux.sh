#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
OUT_DIR="${2:-$ROOT/dist}"
VERSION="${CRAKBIT_VERSION:-0.1.0-testnet}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "package-linux.sh currently supports Linux only" >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64|amd64) ARCH="x86_64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *)
    echo "unsupported Linux architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

for bin in crakbitd crakbit-cli; do
  if [[ ! -x "$BUILD_DIR/bin/$bin" ]]; then
    echo "missing executable: $BUILD_DIR/bin/$bin" >&2
    exit 1
  fi
done

for helper in crakbit-start crakbit-mine crakminer crakminer-native.py build-native-miner.sh install-package.sh; do
  if [[ ! -f "$ROOT/scripts/$helper" ]]; then
    echo "missing helper: scripts/$helper" >&2
    exit 1
  fi
done

if [[ ! -d "$ROOT/.work/crakbit/src/crypto/yespower" ]]; then
  echo "materialized yespower source not found; run scripts/bootstrap.sh and scripts/materialize-locked.sh first" >&2
  exit 1
fi

# CRAK-013 hashes block headers outside crakbitd. Build the standalone scanner
# from the same exact pinned yespower checkout used by the node materializer.
bash "$ROOT/scripts/build-native-miner.sh" "$BUILD_DIR/bin/crakminer-scan" >/dev/null

PKG="crakbit-core-${VERSION}-linux-${ARCH}"
STAGE_PARENT="$OUT_DIR/.stage-$PKG"
STAGE="$STAGE_PARENT/$PKG"
ARCHIVE="$OUT_DIR/$PKG.tar.gz"

rm -rf "$STAGE_PARENT"
mkdir -p "$STAGE/bin" "$STAGE/share/doc/crakbit-core" "$STAGE/share/licenses/crakbit-core" "$STAGE/share/licenses/bitcoin-core" "$STAGE/share/licenses/yespower"

install -m 0755 "$BUILD_DIR/bin/crakbitd" "$STAGE/bin/crakbitd"
install -m 0755 "$BUILD_DIR/bin/crakbit-cli" "$STAGE/bin/crakbit-cli"
install -m 0755 "$BUILD_DIR/bin/crakminer-scan" "$STAGE/bin/crakminer-scan"
install -m 0755 "$ROOT/scripts/crakbit-start" "$STAGE/bin/crakbit-start"
install -m 0755 "$ROOT/scripts/crakbit-mine" "$STAGE/bin/crakbit-mine"
install -m 0755 "$ROOT/scripts/crakminer" "$STAGE/bin/crakminer"
install -m 0755 "$ROOT/scripts/crakminer-native.py" "$STAGE/bin/crakminer-native"
install -m 0755 "$ROOT/scripts/install-package.sh" "$STAGE/install.sh"

cp "$ROOT/README.md" "$STAGE/share/doc/crakbit-core/README.md"
cp "$ROOT/docs/BUILD.md" "$STAGE/share/doc/crakbit-core/BUILD.md"
cp "$ROOT/docs/CONSENSUS.md" "$STAGE/share/doc/crakbit-core/CONSENSUS.md"
cp "$ROOT/LICENSE" "$STAGE/share/licenses/crakbit-core/LICENSE"

if [[ -f "$ROOT/.work/crakbit/COPYING" ]]; then
  cp "$ROOT/.work/crakbit/COPYING" "$STAGE/share/licenses/bitcoin-core/COPYING"
fi

# yespower licensing is carried in the upstream source headers. Include the exact
# vendored files used by this build so binary distributions retain those notices.
for file in yespower-opt.c yespower-platform.c yespower.h sha256.c sha256.h sysendian.h insecure_memzero.h README; do
  cp "$ROOT/.work/crakbit/src/crypto/yespower/$file" "$STAGE/share/licenses/yespower/$file"
done

(
  cd "$STAGE"
  find bin share -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

mkdir -p "$OUT_DIR"
rm -f "$ARCHIVE" "$ARCHIVE.sha256"
tar -C "$STAGE_PARENT" -czf "$ARCHIVE" "$PKG"
(
  cd "$OUT_DIR"
  sha256sum "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256"
)
rm -rf "$STAGE_PARENT"

printf '%s\n' "$ARCHIVE"
printf '%s\n' "$ARCHIVE.sha256"
