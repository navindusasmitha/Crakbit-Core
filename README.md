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
- CRAK-012: packaged `crakminer` RPC mining controller with configurable workers, finite/continuous mining, per-worker duty-cycle CPU limiting, sibling/stale handling, and active-chain height quota tracking
- CRAK-013: native external yespower miner path using `getblocktemplate`, custom BIP34/SegWit coinbase construction, txid merkle assembly, native multi-thread nonce scanning, `submitblock`, deterministic scanner vectors, and packaged end-to-end mining smoke
- CRAK-014: Stratum V1 subset pool server + external CPU worker, unique per-session extranonces, native yespower share verification, block submission, two-worker regtest smoke, and package integration

## Build a Linux testnet package

On a Linux machine with the required build dependencies installed:

```bash
bash scripts/build-linux.sh
```

This fetches the exact pinned upstreams, materializes the Crakbit source tree, builds the wallet-enabled daemon/CLI and native yespower scanner, and writes a versioned package under `dist/`.

The package contains:

```text
bin/crakbitd
bin/crakbit-cli
bin/crakbit-start
bin/crakbit-mine
bin/crakminer
bin/crakminer-native
bin/crakminer-scan
bin/crakpool
bin/crakminer-stratum
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

Then ensure `~/.local/bin` is in your `PATH`. Python 3 is used for template/RPC/Stratum orchestration; yespower hashing itself runs in native `crakminer-scan`.

Start an isolated local regtest node:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakbit-start regtest
```

Create a wallet:

```bash
crakbit-cli -regtest -datadir="$HOME/.crakbit-regtest" createwallet miner
```

Start the Crakbit testnet node:

```bash
crakbit-start testnet4
```

`crakbit-start` binds RPC to localhost. A public seed set is intentionally not shipped yet; an explicit peer can be supplied with `CRAKBIT_ADDNODE=host:port` once independent testnet nodes are available.

## Native CPU mining — CRAK-013

`crakminer-native` asks `crakbitd` for a block template, constructs the coinbase and merkle root outside the node, sends the canonical 80-byte header to native yespower worker threads, inserts a solved nonce, then submits the complete block through `submitblock`.

Low-end CPU example:

```bash
crakminer-native \
  --network testnet4 \
  --wallet miner \
  --threads 1 \
  --cpu-limit 30
```

Four native workers with a finite target:

```bash
crakminer-native \
  --network testnet4 \
  --wallet miner \
  --threads 4 \
  --cpu-limit 75 \
  --blocks 2
```

`--cpu-limit` is an approximate duty cycle per native worker rather than an OS-enforced CPU quota. `--batch-hashes` controls how much nonce work is attempted before refreshing the block template/extranonce.

The older `crakminer` command remains available as the CRAK-012 RPC-controller test/helper path.

## Stratum pool — CRAK-014

Create/load a wallet on the node for the pool payout address, then start a localhost pool:

```bash
crakpool \
  --network testnet4 \
  --wallet pool \
  --listen 127.0.0.1 \
  --port 3333 \
  --share-difficulty 0.0001
```

Connect a worker on the same machine:

```bash
crakminer-stratum \
  --pool 127.0.0.1:3333 \
  --worker worker1 \
  --threads 1 \
  --cpu-limit 50
```

For a controlled private testnet/LAN pool, bind `crakpool` to the server's reachable interface and point each worker at `SERVER_IP:3333`. Keep the node RPC port private; miners only need the Stratum port.

CRAK-014 implements `mining.subscribe`, `mining.authorize`, `mining.set_difficulty`, `mining.notify`, and `mining.submit`. Each TCP session receives a unique `extranonce1`; the worker rotates `extranonce2`, preventing separate machines from intentionally scanning the same header/nonce space.

**Current pool limitation:** the whole block coinbase pays one configured pool wallet/address. CRAK-014 does not yet include persistent share accounting, proportional/PPLNS payouts, automatic worker payments, vardiff, TLS/auth hardening, or guaranteed compatibility with unrelated third-party Stratum miners. Do not expose this first pool implementation as a production public service.

See `docs/POOL.md` for the pool architecture and deployment notes.

## Verification

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
python3 tests/stratum_protocol_unit.py
```

CI additionally proves the pinned yespower output, canonical block hash, genesis, ASERT, subsidy, three-node reorg behavior, wallet persistence, native scanner genesis vector, native `getblocktemplate`/`submitblock` mining, CRAK-012 sibling-race handling, CRAK-014 Stratum protocol vectors, two sequential external pool workers, and installed Linux package pool/mining paths.

## Network status

Bitcoin mainnet, Bitcoin testnet3 and signet remain unavailable as user-selectable Crakbit networks. The current usable development networks are Crakbit testnet4 and regtest.

Bitcoin testnet4 minimum-chain-work and assume-valid checkpoints are not inherited; both are zero for the fresh Crakbit testnet. Crakbit testnet currently has no hard-coded Bitcoin DNS seeds.

## Monetary rounding

Crakbit keeps Bitcoin-style integer right-shift halvings. Starting from 500,000,000 satoshis per block, the final non-zero subsidy era pays 1 satoshi per block and subsidy becomes zero at height 60,900,000. Because every halving truncates integer satoshis, the exact subsidy sum is 2,099,999,972,700,000 satoshis (20,999,999.72700000 CRAK), slightly below the nominal 21 million geometric limit.

The custom testnet and regtest genesis blocks have a **zero CRAK reward**, so they create no premine.

## Important status

This repository is still a **v0.1 engineering/testnet project**. It is **not mainnet-ready** and does not claim production safety.

The remaining major gates include independent public testnet nodes, longer-duration CPU mining/reorg operation, reproducible cross-platform release builds, ARM64 runtime validation, hardened persistent pool accounting/payout infrastructure, broader miner interoperability testing, and external security/code review.

No mainnet genesis block will be finalized until those gates pass review in addition to the consensus/network gates already covered by CI.

## License

Crakbit project files are MIT licensed. Upstream Bitcoin Core remains under its own MIT notices. yespower source retains its upstream BSD-style notices; the Linux package carries the exact vendored yespower source/header material used by the build so those notices remain with binary distributions. CRAK-007 ASERT is adapted from the MIT-licensed Bitcoin Cash/Bitcoin ABC ASERT reference design with Crakbit-specific wide-intermediate handling for its easy CPU-test target.
