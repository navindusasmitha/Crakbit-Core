#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${1:-$HOME/.local}"

for file in crakbitd crakbit-cli crakbit-start crakbit-mine crakminer crakminer-native crakminer-scan crakpool crakpool-stats crakpool-base.py crakminer-stratum; do
  if [[ ! -f "$ROOT/bin/$file" ]]; then
    echo "missing package file: bin/$file" >&2
    exit 1
  fi
done

install -d "$PREFIX/bin"
for file in crakbitd crakbit-cli crakbit-start crakbit-mine crakminer crakminer-native crakminer-scan crakpool crakpool-stats crakminer-stratum; do
  install -m 0755 "$ROOT/bin/$file" "$PREFIX/bin/$file"
done
install -m 0644 "$ROOT/bin/crakpool-base.py" "$PREFIX/bin/crakpool-base.py"

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

CRAK-013 native yespower mining example:
  $PREFIX/bin/crakminer-native --network testnet4 --wallet miner --threads 1 --cpu-limit 50

CRAK-015 accounting/vardiff pool example:
  $PREFIX/bin/crakpool --network testnet4 --wallet pool --listen 127.0.0.1 --port 3333 --payout-mode pplns

CRAK-014/015 worker example:
  $PREFIX/bin/crakminer-stratum --pool 127.0.0.1:3333 --worker worker1 --threads 1 --cpu-limit 50

Inspect the pool ledger:
  $PREFIX/bin/crakpool-stats --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\"
EOF
