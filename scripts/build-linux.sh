#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBS="${CRAKBIT_BUILD_JOBS:-2}"
BUILD_DIR="${CRAKBIT_BUILD_DIR:-$ROOT/.work/crakbit-build}"
OUT_DIR="${CRAKBIT_OUT_DIR:-$ROOT/dist}"

for cmd in git python3 cmake cc c++ tar sha256sum; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing required command: $cmd" >&2
    exit 1
  fi
done

bash "$ROOT/scripts/bootstrap.sh"
bash "$ROOT/scripts/materialize-locked.sh"

cmake -S "$ROOT/.work/crakbit" -B "$BUILD_DIR" \
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

cmake --build "$BUILD_DIR" --target bitcoind bitcoin-cli --parallel "$JOBS"

test -x "$BUILD_DIR/bin/crakbitd"
test -x "$BUILD_DIR/bin/crakbit-cli"

bash "$ROOT/scripts/package-linux.sh" "$BUILD_DIR" "$OUT_DIR"
