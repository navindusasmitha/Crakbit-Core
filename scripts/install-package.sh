#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${1:-$HOME/.local}"

for file in crakbitd crakbit-cli crakbit-start crakbit-mine; do
  if [[ ! -f "$ROOT/bin/$file" ]]; then
    echo "missing package file: bin/$file" >&2
    exit 1
  fi
done

install -d "$PREFIX/bin"
install -m 0755 "$ROOT/bin/crakbitd" "$PREFIX/bin/crakbitd"
install -m 0755 "$ROOT/bin/crakbit-cli" "$PREFIX/bin/crakbit-cli"
install -m 0755 "$ROOT/bin/crakbit-start" "$PREFIX/bin/crakbit-start"
install -m 0755 "$ROOT/bin/crakbit-mine" "$PREFIX/bin/crakbit-mine"

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
EOF
