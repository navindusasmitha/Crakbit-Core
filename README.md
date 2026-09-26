# Crakbit Core

Crakbit Core is a Bitcoin-style UTXO Proof-of-Work blockchain project focused on CPU mining.

## v0.1 consensus profile

- Upstream base: **Bitcoin Core v31.1** (pinned commit)
- PoW library: **Openwall yespower** (pinned commit)
- PoW profile: **YESPOWER_1_0, N=2048, r=8**
- Block-header identity / PoW hash: **yespower over the canonical 80-byte header**
- Target block interval: **60 seconds**
- Initial block subsidy: **5 CRAK**
- Halving interval: **2,100,000 blocks**
- Nominal geometric cap: **21,000,000 CRAK**
- Exact integer-rounded subsidy total: **20,999,999.72700000 CRAK**
- Coinbase maturity: **100 blocks**
- Testnet difficulty: **ASERT**, 2-hour (7,200 second) half-life
- ASERT anchor: **genesis conceptual parent one target-spacing before genesis**
- Regtest difficulty: **no retargeting** for deterministic local testing
- Premine: **0**

## Implemented milestones

- CRAK-004: pinned yespower build integration
- CRAK-005: yespower block-header identity hash + deterministic vector
- CRAK-006: isolated Crakbit testnet/regtest identity + zero-reward custom genesis blocks
- CRAK-007: integer-only ASERT testnet difficulty + frozen Python/C++ vectors
- CRAK-008: 5 CRAK subsidy, 2,100,000-block halving, 100-block maturity, zero premine + compiled boundary vectors
- CRAK-009: full `crakbitd` / `crakbit-cli` build, CPU mining RPC, three-node sync, reorg and invalid-block smoke
- CRAK-010: wallet send/receive/restart persistence smoke
- CRAK-011: Linux package builder, installer, safe node launcher, checksums and package smoke
- CRAK-012: packaged RPC mining controller with worker and CPU-duty-cycle controls
- CRAK-013: native external yespower miner using `getblocktemplate` → native nonce scanning → `submitblock`
- CRAK-014: Stratum V1 subset pool + external CPU workers, unique extranonces, share verification and block submission
- CRAK-015: persistent SQLite share/block/credit accounting, proportional and PPLNS reward accounting, worker statistics/hashrate estimates, persisted per-worker difficulty and vardiff
- CRAK-016: canonical-chain reward reconciliation, worker payout-address registration, 100-confirmation maturity gating, deterministic non-broadcast payout batches and reorg invalidation

## Build a Linux testnet package

```bash
bash scripts/build-linux.sh
```

The package includes:

```text
bin/crakbitd
bin/crakbit-cli
bin/crakbit-start
bin/crakbit-mine
bin/crakminer
bin/crakminer-native
bin/crakminer-scan
bin/crakpool
bin/crakpool-stats
bin/crakpool-payout
bin/crakminer-stratum
install.sh
SHA256SUMS
share/doc/crakbit-core/
share/licenses/
```

Install an extracted package:

```bash
bash install.sh ~/.local
```

Python 3 handles template/RPC/Stratum/accounting/reconciliation orchestration. yespower hashing itself runs in the native `crakminer-scan` binary.

## Node and native CPU mining

Start regtest:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakbit-start regtest
crakbit-cli -regtest -datadir="$HOME/.crakbit-regtest" createwallet miner
```

Start testnet4:

```bash
crakbit-start testnet4
```

Low-end native CPU mining example:

```bash
crakminer-native \
  --network testnet4 \
  --wallet miner \
  --threads 1 \
  --cpu-limit 30
```

`--cpu-limit` is an approximate per-worker duty cycle, not a kernel-enforced quota.

## Pool mining — CRAK-014 / CRAK-015 / CRAK-016

CRAK-015 makes `crakpool` the persistent accounting/vardiff pool command. The CRAK-014 protocol engine remains packaged internally as `crakpool-base.py`. CRAK-016 adds a separate `crakpool-payout` reconciliation/planning tool so ledger review is isolated from the live Stratum process.

Start a localhost PPLNS pool:

```bash
crakpool \
  --network testnet4 \
  --wallet pool \
  --listen 127.0.0.1 \
  --port 3333 \
  --share-difficulty 0.0001 \
  --payout-mode pplns \
  --pplns-shares 1000 \
  --pool-fee-bps 0
```

Or use proportional accounting:

```bash
crakpool \
  --network testnet4 \
  --wallet pool \
  --port 3333 \
  --share-difficulty 0.0001 \
  --payout-mode proportional
```

Connect another CPU machine:

```bash
crakminer-stratum \
  --pool POOL_IP:3333 \
  --worker pc1 \
  --threads 1 \
  --cpu-limit 30
```

For LAN/testnet deployment, expose only the Stratum port to miners and keep the Crakbit node RPC private.

### CRAK-015 accounting

By default the ledger is stored under the selected node datadir as:

```text
crakpool-testnet4.sqlite3
```

A custom path can be supplied with `--db`.

The SQLite ledger persists:

- workers and their current share difficulty;
- accepted/rejected share counts;
- accepted share difficulty and hashes;
- found blocks;
- pool accounting fee amounts;
- deterministic per-worker pending reward credits.

Reward accounting modes:

- `proportional`: difficulty-weighted shares since the previous found block;
- `pplns`: difficulty-weighted last-N accepted shares, controlled by `--pplns-shares`.

`--pool-fee-bps` is an **accounting-only** fee. `100` means 1%. The default is `0`.

Inspect the ledger:

```bash
crakpool-stats \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  --window 600
```

JSON output:

```bash
crakpool-stats --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" --json
```

The hashrate value is an estimate derived from accepted share difficulty over the selected time window.

### Vardiff

Vardiff is enabled by default. It aims for roughly one accepted share every 15 seconds per worker, persists the worker difficulty, uses hysteresis, and limits each adjustment to between 0.25x and 4x.

Useful controls:

```text
--no-vardiff
--vardiff-min <difficulty>
--vardiff-max <difficulty>
--vardiff-target-seconds 15
--vardiff-retarget-seconds 90
```

### CRAK-016 payout address + reconciliation

Register a known worker payout address. The selected node validates that address for the requested network:

```bash
crakpool-payout \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  register \
  --network testnet4 \
  --worker pc1 \
  --address <CRAK_ADDRESS>
```

Reconcile pool-found blocks against the current canonical chain:

```bash
crakpool-payout \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  reconcile \
  --network testnet4
```

If a reorg removes a credited block, CRAK-016 marks that block non-canonical, moves its unpaid credits to `orphaned`, and invalidates any unbroadcast payout plan that depended on those credits.

### CRAK-016 mature payout planning

Create an auditable payout batch after canonical source blocks reach the maturity threshold:

```bash
crakpool-payout \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  plan \
  --network testnet4 \
  --wallet pool \
  --maturity 100 \
  --minimum-sats 100000 \
  --max-outputs 100
```

When `--wallet` is supplied, the planner checks the wallet's trusted balance against the selected payout amount plus the configured fee reserve. Selected credits atomically move from `pending` to `planned`, so they cannot enter two active plans.

Inspect or cancel an unbroadcast plan:

```bash
crakpool-payout --db <DB> status
crakpool-payout --db <DB> show --batch <BATCH_ID>
crakpool-payout --db <DB> cancel --batch <BATCH_ID>
```

### Important payout boundary

CRAK-016 still does **not** construct, sign, or broadcast worker payout transactions. Block coinbase continues to pay the configured pool wallet/address. A CRAK-016 batch is an accounting/reconciliation plan, not proof of an on-chain payment.

Transaction construction, fee selection, signing, broadcast, txid persistence, crash recovery, conflict/replacement handling and final `paid` credit transitions belong to a separate reviewed milestone so an accounting or reorg bug cannot directly move funds.

The pool remains testnet engineering infrastructure. Worker passwords are not production-grade authentication, TLS/rate limiting/bounded verification work and broader third-party Stratum compatibility still need hardening.

## Verification

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
python3 tests/stratum_protocol_unit.py
python3 tests/pool_accounting_unit.py
python3 tests/payout_planner_unit.py
```

CI covers consensus vectors, three-node/reorg behavior, wallet persistence, native mining, CRAK-014 two-worker Stratum mining, CRAK-015 accounting/vardiff and SQLite restart persistence, CRAK-016 maturity/reorg payout planning, reward-credit conservation, and installed-package pool/mining/planner paths.

## Network status

Bitcoin mainnet, Bitcoin testnet3 and signet remain unavailable as user-selectable Crakbit networks. The current usable development networks are Crakbit testnet4 and regtest.

Crakbit testnet currently has no inherited Bitcoin DNS seeds, minimum-chain-work, or assume-valid checkpoint.

## Monetary rounding

Crakbit keeps Bitcoin-style integer right-shift halvings. Starting from 500,000,000 satoshis per block, subsidy becomes zero at height 60,900,000. Integer truncation makes the exact subsidy sum 2,099,999,972,700,000 satoshis (20,999,999.72700000 CRAK), slightly below the nominal 21 million geometric limit.

The custom testnet and regtest genesis blocks have a **zero CRAK reward**, so they create no premine.

## Important status

This repository is still a **v0.1 engineering/testnet project**. It is **not mainnet-ready** and does not claim production safety.

Remaining major gates include independent public testnet nodes, sustained mining/reorg operation, reproducible cross-platform builds, ARM64 runtime validation, transaction payout execution hardening, public-pool security controls, broader miner interoperability, and external security/code review.

No mainnet genesis block will be finalized until those gates pass review.

## License

Crakbit project files are MIT licensed. Upstream Bitcoin Core remains under its own MIT notices. yespower source retains its upstream BSD-style notices; binary packages carry the exact vendored yespower source/header material used by the build. CRAK-007 ASERT is adapted from the MIT-licensed Bitcoin Cash/Bitcoin ABC ASERT reference design with Crakbit-specific wide-intermediate handling for the easy CPU-test target.
