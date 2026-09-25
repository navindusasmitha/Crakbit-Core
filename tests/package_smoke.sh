#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
TMP="$(mktemp -d)"
OUT="$TMP/out"
EXTRACT="$TMP/extract"
PREFIX="$TMP/prefix"
DATADIR="$TMP/datadir"

cleanup() {
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

for bin in crakbitd crakbit-cli crakbit-start crakbit-mine crakminer; do
  test -x "$PREFIX/bin/$bin"
done

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

# CRAK-012: prove the packaged controller can run multiple workers, apply a
# duty-cycle limit, recover from any sibling/stale work, and stop only after two
# blocks are confirmed on the active chain.
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

"$PREFIX/bin/crakbit-cli" -regtest "-datadir=$DATADIR" stop >/dev/null
sleep 1

echo "CRAK-012 controlled CPU miner smoke: OK height=$HEIGHT"
