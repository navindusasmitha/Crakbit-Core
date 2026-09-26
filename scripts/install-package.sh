#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${1:-$HOME/.local}"

for file in crakbitd crakbit-cli crakbit-start crakbit-mine crakminer crakminer-native crakminer-scan crakpool crakpool-stats crakpool-payout crakpool-paytx crakpool-payguard crakpool-payops crakpool-base.py crakminer-stratum; do
  [[ -f "$ROOT/bin/$file" ]] || { echo "missing package file: bin/$file" >&2; exit 1; }
done

install -d "$PREFIX/bin"
for file in crakbitd crakbit-cli crakbit-start crakbit-mine crakminer crakminer-native crakminer-scan crakpool crakpool-stats crakpool-payout crakpool-paytx crakpool-payguard crakpool-payops crakminer-stratum; do
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

CRAK-016 register a worker payout address:
  $PREFIX/bin/crakpool-payout --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\" register --network testnet4 --worker worker1 --address <CRAK_ADDRESS>

CRAK-016 create a mature non-broadcast payout plan:
  $PREFIX/bin/crakpool-payout --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\" plan --network testnet4 --wallet pool --minimum-sats 100000

CRAK-017 build an operator-controlled funded PSBT (does not sign or broadcast):
  $PREFIX/bin/crakpool-paytx --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\" build-psbt --network testnet4 --wallet pool --batch <BATCH_ID> --fee-rate 1.0

CRAK-018 preflight immediately before external signing/broadcast:
  $PREFIX/bin/crakpool-payguard --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\" preflight --network testnet4 --wallet pool --batch <BATCH_ID> --max-fee-sats <MAX_FEE_SATS>

After signing/broadcasting with your own wallet tooling, attach the resulting txid through the fresh-preflight guard:
  $PREFIX/bin/crakpool-payguard --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\" guarded-attach --batch <BATCH_ID> --txid <TXID>

Cancel only a PSBT you have verified was never signed or broadcast:
  $PREFIX/bin/crakpool-payguard --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\" cancel --network testnet4 --wallet pool --batch <BATCH_ID> --confirm-not-broadcast

CRAK-019 payout operations summary:
  $PREFIX/bin/crakpool-payops --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\" summary

CRAK-019 list batches and next operator actions:
  $PREFIX/bin/crakpool-payops --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\" list

Refresh one broadcast/confirmed payment explicitly (never signs, broadcasts, or settles):
  $PREFIX/bin/crakpool-payops --db \"$HOME/.crakbit/crakpool-testnet4.sqlite3\" refresh --network testnet4 --wallet pool --batch <BATCH_ID>
EOF
