# Build / Development Bootstrap

## Linux prerequisites

Install Git, Python 3, CMake, a C/C++ toolchain, pkg-config, libevent, Boost and SQLite development headers.

For the Ubuntu CI path the project installs:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake pkg-config libevent-dev libboost-dev libsqlite3-dev
```

## One-command Linux build/package

```bash
bash scripts/build-linux.sh
```

Optional controls:

```bash
CRAKBIT_BUILD_JOBS=4 bash scripts/build-linux.sh
CRAKBIT_BUILD_DIR=/tmp/crakbit-build CRAKBIT_OUT_DIR=/tmp/crakbit-dist bash scripts/build-linux.sh
```

The script fetches pinned upstreams, materializes Crakbit, configures a wallet-enabled daemon/CLI build, compiles `crakbitd` and `crakbit-cli`, builds the native yespower scanner, then calls `scripts/package-linux.sh`.

Current package naming is:

```text
crakbit-core-0.1.0-testnet-linux-x86_64.tar.gz
crakbit-core-0.1.0-testnet-linux-x86_64.tar.gz.sha256
```

On an ARM64 Linux builder the same packager maps the architecture to `arm64`, but ARM64 compilation/runtime validation is still a separate gate.

## Manual pinned-source workflow

Fetch upstreams:

```bash
bash scripts/bootstrap.sh
```

The script creates:

- `.work/bitcoin` at the exact Bitcoin Core v31.1 commit locked in `SOURCE_LOCK.json`;
- `.work/yespower` at the exact Openwall yespower commit locked in `SOURCE_LOCK.json`.

Materialize Crakbit consensus/node source:

```bash
bash scripts/materialize-locked.sh
```

The resulting tree is `.work/crakbit`. `.work/materialized-source.txt` records the locked upstream commits and active Crakbit consensus profile.

Configure/build the daemon and CLI manually:

```bash
cmake -S .work/crakbit -B .work/crakbit-build \
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

cmake --build .work/crakbit-build --target bitcoind bitcoin-cli --parallel 2
```

Build only the native yespower scanner after bootstrap:

```bash
bash scripts/build-native-miner.sh .work/crakbit-build/bin/crakminer-scan
```

Package an existing build:

```bash
bash scripts/package-linux.sh .work/crakbit-build dist
```

## Package contents and install

The Linux package includes:

```text
crakbitd
crakbit-cli
crakbit-start
crakbit-mine
crakminer
crakminer-native
crakminer-scan
crakpool
crakminer-stratum
```

It also includes the installer, internal checksums, project docs, Crakbit license, Bitcoin Core COPYING file when present, and the exact vendored yespower source/header material carrying the upstream redistribution notices.

After extracting:

```bash
bash install.sh ~/.local
```

The installer copies binaries to `~/.local/bin` and documentation/license material to `~/.local/share/crakbit-core`.

## Node/miner helpers

Start regtest:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakbit-start regtest
```

Create a wallet:

```bash
crakbit-cli -regtest -datadir="$HOME/.crakbit-regtest" createwallet miner
```

Start Crakbit testnet4:

```bash
crakbit-start testnet4
```

The launcher explicitly keeps RPC on `127.0.0.1`. Set `CRAKBIT_ADDNODE=host:port` to provide one explicit testnet peer; no Bitcoin seed is inherited.

### CRAK-012 RPC controller

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakminer \
  --network regtest \
  --wallet miner \
  --threads 2 \
  --cpu-limit 50 \
  --blocks 2
```

`crakminer` uses concurrent short mining RPC calls. Its finite mode is controlled by start/target active-chain height plus in-flight reservations, so two competing sibling solutions cannot satisfy the requested height increase early.

### CRAK-013 native yespower miner

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakminer-native \
  --network regtest \
  --wallet miner \
  --threads 2 \
  --cpu-limit 50 \
  --blocks 2
```

CRAK-013 no longer asks `crakbitd` to perform the hashing loop. `crakminer-native` obtains `getblocktemplate`, constructs the BIP34/SegWit coinbase and txid merkle root, then launches `crakminer-scan`. The native scanner partitions nonce work across C++ worker threads and runs yespower directly. Solved blocks are serialized and returned to the node through `submitblock` for full consensus validation.

### CRAK-014 Stratum pool and worker

Start a pool against a locally reachable Crakbit node/wallet:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakpool \
  --network regtest \
  --wallet miner \
  --listen 127.0.0.1 \
  --port 3333 \
  --share-difficulty 0.000000001
```

Connect an external worker:

```bash
crakminer-stratum \
  --pool 127.0.0.1:3333 \
  --worker worker1 \
  --threads 2 \
  --cpu-limit 50
```

For testnet/LAN use, change `--listen` to a reachable server interface and point workers at that server address. Do not expose the node RPC port; only the Stratum TCP port needs to be reachable by miners.

The CRAK-014 server implements a limited Stratum V1-compatible JSON-lines surface for subscription, authorization, difficulty, job notification and share submission. Pool payout is one configured address. Persistent share accounting, automated payouts, vardiff and production public-pool hardening are not part of CRAK-014.

See `docs/POOL.md` for details.

## Verification

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
python3 tests/stratum_protocol_unit.py
```

CI covers:

- pinned yespower output;
- canonical 80-byte block-header hash;
- frozen Crakbit genesis blocks;
- CRAK-007 ASERT vectors and chain routing;
- CRAK-008 subsidy boundaries, exact supply sum and maturity;
- CRAK-009 three-node sync/mining/reorg/invalid-block rejection;
- CRAK-010 wallet send/receive/restart persistence;
- CRAK-011 package checksum, extraction, install, packaged regtest startup and single-request mining helper;
- CRAK-012 multi-worker RPC controller and sibling-race-safe finite chain-height target;
- CRAK-013 standalone native scanner genesis vector;
- CRAK-013 real `getblocktemplate` → native yespower → `submitblock` regtest mining;
- CRAK-014 BIP34/difficulty/merkle protocol unit vectors;
- CRAK-014 two external Stratum worker sessions across refreshed pool jobs;
- installed-package CRAK-011/012/013/014 mining and pool paths.

Separate fast native-miner and Stratum workflows verify their local vectors without waiting for the full Bitcoin node compile.

Passing these gates still does not make the project mainnet-ready. Independent public testnet operation, sustained mining/reorg testing, reproducible cross-platform builds, ARM64 runtime validation, hardened persistent pool payouts/accounting, third-party miner interoperability and external review remain required.
