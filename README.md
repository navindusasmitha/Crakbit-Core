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
- CRAK-009: full `crakbitd` / `crakbit-cli` build, yespower CPU mining RPC, three-node sync, competing-fork reorg, and invalid-block rejection smoke
- CRAK-010: wallet-enabled build, 1 CRAK send/receive confirmation, clean restart, explicit wallet reload, balance and transaction-history persistence smoke
- CRAK-011: Linux package builder, installer, safe node launcher, single-request CPU mining helper, checksums, bundled license material, and package install/start/mine smoke
- CRAK-012: packaged `crakminer` RPC mining controller with configurable workers, finite/continuous mining, per-worker duty-cycle CPU limiting, stale/side-block detection, and active-chain quota tracking

## Build a Linux testnet package

On a Linux machine with the required build dependencies installed:

```bash
bash scripts/build-linux.sh
```

This fetches the exact pinned upstreams, materializes the Crakbit source tree, builds the wallet-enabled daemon/CLI, and writes a versioned package under `dist/`.

The package contains:

```text
bin/crakbitd
bin/crakbit-cli
bin/crakbit-start
bin/crakbit-mine
bin/crakminer
install.sh
SHA256SUMS
share/doc/crakbit-core/
share/licenses/
```

The archive also gets a separate `.sha256` checksum file.

## Install an extracted package

```bash
bash install.sh ~/.local
```

Then ensure `~/.local/bin` is in your `PATH`.

Start an isolated local regtest node:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakbit-start regtest
```

Create a wallet and mine one local CPU block:

```bash
crakbit-cli -regtest -datadir="$HOME/.crakbit-regtest" createwallet miner
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakbit-mine miner 1 regtest
```

Start the Crakbit testnet node:

```bash
crakbit-start testnet4
```

`crakbit-start` binds RPC to localhost. A public seed set is intentionally not shipped yet; an explicit peer can be supplied with `CRAKBIT_ADDNODE=host:port` once independent testnet nodes are available.

## Controlled CPU mining

`crakminer` is the CRAK-012 miner controller. Hashing still happens inside `crakbitd` through the same yespower mining RPC used by consensus tests; the controller adds short-work refresh, multiple workers, active-chain verification, and an approximate duty-cycle limit.

Example: one low-end CPU worker at roughly 30% duty cycle:

```bash
crakminer --network testnet4 --wallet miner --threads 1 --cpu-limit 30
```

Example: four workers and stop after two active-chain blocks:

```bash
crakminer --network testnet4 --wallet miner --threads 4 --cpu-limit 75 --blocks 2
```

`--cpu-limit` is applied per worker and is a duty-cycle controller rather than an OS-enforced CPU quota. Multiple workers can occasionally solve sibling blocks from the same tip; those stale/side blocks are detected and are not counted toward `--blocks`.

A future native miner can move template handling and nonce partitioning out of the node and add Stratum/pool support without changing Crakbit consensus.

## Verification

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
```

CI additionally compiles and executes the yespower, block-header, genesis, ASERT, subsidy, full-node, three-node network, wallet restart, Linux package usability, and controlled multi-worker miner smoke paths.

## Network status

Bitcoin mainnet, Bitcoin testnet3 and signet remain unavailable as user-selectable Crakbit networks. The current usable development networks are Crakbit testnet4 and regtest.

Bitcoin testnet4 minimum-chain-work and assume-valid checkpoints are not inherited; both are zero for the fresh Crakbit testnet. Crakbit testnet currently has no hard-coded Bitcoin DNS seeds.

## Monetary rounding

Crakbit keeps Bitcoin-style integer right-shift halvings. Starting from 500,000,000 satoshis per block, the final non-zero subsidy era pays 1 satoshi per block and subsidy becomes zero at height 60,900,000. Because every halving truncates integer satoshis, the exact subsidy sum is 2,099,999,972,700,000 satoshis (20,999,999.72700000 CRAK), slightly below the nominal 21 million geometric limit.

The custom testnet and regtest genesis blocks have a **zero CRAK reward**, so they create no premine.

## Important status

This repository is still a **v0.1 engineering/testnet project**. It is **not mainnet-ready** and does not claim production safety.

The remaining major gates include independent public testnet nodes, longer-duration CPU mining/reorg operation, reproducible cross-platform release builds, ARM64 runtime validation, a native template/nonce-partitioned miner with pool/Stratum support, and external security/code review.

No mainnet genesis block will be finalized until those gates pass review in addition to the consensus/network gates already covered by CI.

## License

Crakbit project files are MIT licensed. Upstream Bitcoin Core remains under its own MIT notices. yespower source retains its upstream BSD-style notices; the Linux package carries the exact vendored yespower source/header material used by the build so those notices remain with binary distributions. CRAK-007 ASERT is adapted from the MIT-licensed Bitcoin Cash/Bitcoin ABC ASERT reference design with Crakbit-specific wide-intermediate handling for its easy CPU-test target.
