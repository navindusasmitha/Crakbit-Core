#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${1:-$HOME/.local}"

for file in crakbitd crakbit-cli crakbit-start crakbit-mine crakminer crakminer-native crakminer-scan; do
  if [[ ! -f "$ROOT/bin/$file" ]]; then
    echo "missing package file: bin/$file" >&2
    exit 1
  fi
done

install -d "$PREFIX/bin"
for file in crakbitd crakbit-cli crakbit-start crakbit-mine crakminer crakminer-native crakminer-scan; do
  install -m 0755 "$ROOT/bin/$file" "$PREFIX/bin/$file"
done

if [[ -d "$ROOT/share" ]]; then
  install -d "$PREFIX/share/crakbit-core"
  cp -R "$ROOT/share/." "$PREFIX/share/crakbit-core/"
fi

cat <<EOF
Crakbit Core installed to: $PREFIX
Binaries: $PREFIX/bin

Start a local regtest node:
  CRAKBIT_DATADIR=\"$HOME/.crakbit-regtest\" $PREFIX/bin/crakbit-start regtest

Start the Crakbit testnet node:
  $PREFIX/bin/crakbit-start testnet4

CRAK-012 RPC-controller mining example:
  $PREFIX/bin/crakminer --network testnet4 --wallet miner --threads 1 --cpu-limit 50

CRAK-013 native yespower mining example (requires Python 3 for template control):
  $PREFIX/bin/crakminer-native --network testnet4 --wallet miner --threads 1 --cpu-limit 50
EOF
