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

The script fetches pinned upstreams, materializes Crakbit, configures a wallet-enabled daemon/CLI build, compiles `crakbitd` and `crakbit-cli`, then calls `scripts/package-linux.sh`.

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

Package an existing build:

```bash
bash scripts/package-linux.sh .work/crakbit-build dist
```

## Package contents and install

The Linux package includes the daemon, CLI, node launcher, single-request mining helper, CRAK-012 `crakminer` controller, install script, internal file checksums, project docs, Crakbit license, Bitcoin Core COPYING file when present, and the exact vendored yespower source/header material carrying the upstream redistribution notices.

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

Create a wallet and mine one block:

```bash
crakbit-cli -regtest -datadir="$HOME/.crakbit-regtest" createwallet miner
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakbit-mine miner 1 regtest
```

Start Crakbit testnet4:

```bash
crakbit-start testnet4
```

The launcher explicitly keeps RPC on `127.0.0.1`. Set `CRAKBIT_ADDNODE=host:port` to provide one explicit testnet peer; no Bitcoin seed is inherited.

For controlled CPU mining:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakminer \
  --network regtest \
  --wallet miner \
  --threads 2 \
  --cpu-limit 50 \
  --blocks 2
```

`crakminer` uses concurrent short mining RPC calls. `--cpu-limit` is an approximate duty cycle per worker, not a kernel-enforced quota. It verifies each returned block is on the active chain before counting it, so sibling/stale work does not satisfy a finite `--blocks` target.

The next miner architecture step is a native template/nonce-partitioned yespower miner with direct block submission and later Stratum support. That can reduce duplicate work between workers while leaving consensus unchanged.

## Verification

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
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
- CRAK-012 packaged multi-worker CPU controller, duty-cycle option and active-chain block quota.

Passing these gates still does not make the project mainnet-ready. Independent public testnet operation, sustained mining/reorg testing, reproducible cross-platform builds, ARM64 runtime validation, a native miner/pool path and external review remain required.
