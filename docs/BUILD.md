# Build / Development Bootstrap

## Linux prerequisites

Install Git, Python 3, CMake, a C/C++ toolchain, pkg-config, libevent, Boost and SQLite development headers.

Ubuntu CI installs:

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

The script fetches pinned upstreams, materializes Crakbit, builds the wallet-enabled daemon/CLI and native yespower scanner, then writes the Linux package under `dist/`.

Current package naming:

```text
crakbit-core-0.1.0-testnet-linux-x86_64.tar.gz
crakbit-core-0.1.0-testnet-linux-x86_64.tar.gz.sha256
```

The packager supports x86_64 and ARM64. CRAK-023 separately proves the native Ubuntu 24.04 ARM64 compile/package/install/runtime path.

## Manual pinned-source workflow

```bash
bash scripts/bootstrap.sh
bash scripts/materialize-locked.sh
```

The bootstrap pins:

- Bitcoin Core v31.1 at the exact commit in `SOURCE_LOCK.json`;
- Openwall yespower at the exact commit in `SOURCE_LOCK.json`.

Materialized source is written to `.work/crakbit` and `.work/materialized-source.txt` records the active source/consensus locks.

Configure/build manually:

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

Build only the native yespower scanner:

```bash
bash scripts/build-native-miner.sh .work/crakbit-build/bin/crakminer-scan
```

Package an existing build:

```bash
bash scripts/package-linux.sh .work/crakbit-build dist
```

## CRAK-022 deterministic package reproducibility

Given identical build binaries, source commit, version and `SOURCE_DATE_EPOCH`, the package layer must emit a byte-identical archive. Run the package-level smoke after preparing release binaries:

```bash
bash tests/package_reproducibility_smoke.sh .work/crakbit-build
```

Each archive includes `share/doc/crakbit-core/BUILD-MANIFEST.json` and internal `SHA256SUMS`.

## CRAK-024 independent cross-builder reproducibility

CRAK-024 goes beyond rebuilding the archive from one binary set. It performs clean independent compilation and packaging in two CI builder lanes, then compares the final release bytes.

Prepare pinned sources for a local builder lane:

```bash
bash scripts/bootstrap.sh
bash scripts/materialize-locked.sh
bash scripts/build-independent-repro.sh local-a
```

The builder normalizes checkout-root paths with GCC file/debug/macro prefix maps and uses the checked-out source commit time as `SOURCE_DATE_EPOCH`. It emits a release archive, sidecar, deterministic `REPRODUCIBILITY-MANIFEST.json` and separate `BUILDER-INFO.json` under `.work/repro-bundles/<builder-id>/` by default.

Compare two independently produced bundles:

```bash
python3 scripts/repro-manifest.py compare \
  --left /path/to/builder-a \
  --right /path/to/builder-b
```

Fast parser/tamper regression test:

```bash
python3 tests/repro_manifest_unit.py
```

The official `Verify Crakbit Independent Reproducibility` workflow uses different GitHub host-image generations for the two builders while keeping the Ubuntu 24.04 container userland/toolchain controlled. This proves the maintained Linux x86_64 controlled-toolchain path; it is not a claim about arbitrary compilers or distributions.

## Installed commands

The Linux package contains:

```text
crakbitd
crakbit-cli
crakbit-start
crakbit-mine
crakminer
crakminer-native
crakminer-scan
crakpool
crakpool-stats
crakpool-payout
crakpool-paytx
crakpool-payguard
crakpool-payops
crakminer-stratum
```

`crakpool-base.py` is installed beside them as the internal CRAK-014 Stratum protocol module used by the CRAK-015 accounting wrapper. Private `.py` copies required by the CRAK-017/018/019 payout dynamic-import chain are also installed beside the extensionless public commands.

Install:

```bash
bash install.sh ~/.local
```

## Node / miner helpers

Start regtest and create a wallet:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakbit-start regtest
crakbit-cli -regtest -datadir="$HOME/.crakbit-regtest" createwallet miner
```

Native CRAK-013 mining:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakminer-native \
  --network regtest \
  --wallet miner \
  --threads 2 \
  --cpu-limit 50 \
  --blocks 2
```

## CRAK-015 accounting / vardiff pool

Start an accounting pool:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakpool \
  --network regtest \
  --wallet miner \
  --listen 127.0.0.1 \
  --port 3333 \
  --share-difficulty 0.000000001 \
  --payout-mode pplns \
  --pplns-shares 1000 \
  --pool-fee-bps 0
```

Connect an external CPU worker:

```bash
crakminer-stratum \
  --pool 127.0.0.1:3333 \
  --worker worker1 \
  --threads 2 \
  --cpu-limit 50
```

For LAN/testnet deployment, expose only the Stratum TCP port. Keep `crakbitd` RPC bound to private/local interfaces.

### Ledger

Default ledger path:

```text
<datadir>/crakpool-<network>.sqlite3
```

Override with:

```bash
--db /path/to/pool.sqlite3
```

The SQLite database uses WAL mode and persists workers, accepted/rejected share counters, accepted-share difficulty/hash, found blocks, accounting fees and per-worker pending credits.

Stats:

```bash
crakpool-stats --db /path/to/pool.sqlite3 --window 600
crakpool-stats --db /path/to/pool.sqlite3 --json
```

Reward accounting:

- `--payout-mode proportional`: difficulty-weighted accepted shares since the previous found block;
- `--payout-mode pplns`: difficulty-weighted last `--pplns-shares` accepted shares;
- `--pool-fee-bps 100`: account for a 1% pool fee; default is zero.

The deterministic largest-remainder allocator conserves every distributable satoshi.

### Vardiff

Vardiff is enabled by default and persists per-worker difficulty. Default target is one accepted share every 15 seconds, with 90-second retarget spacing, hysteresis and a maximum single-step change of 4x up / 0.25x down.

Controls:

```text
--no-vardiff
--vardiff-min <difficulty>
--vardiff-max <difficulty>
--vardiff-target-seconds <seconds>
--vardiff-retarget-seconds <seconds>
```

### Payment safety boundary

The normal payout path does not sign or broadcast automatically. CRAK-016 through CRAK-019 separate reconciliation/planning, PSBT construction, preflight/recovery and operations monitoring. CRAK-020 signs/broadcasts only inside isolated regtest CI to prove the complete state machine.

## Verification

Fast checks:

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
python3 tests/stratum_protocol_unit.py
python3 tests/pool_accounting_unit.py
python3 tests/payout_planner_unit.py
python3 tests/paytx_unit.py
python3 tests/payguard_unit.py
python3 tests/payops_unit.py
python3 tests/repro_manifest_unit.py
python3 scripts/verify-repo-integrity.py
```

Full/dedicated CI additionally covers:

- pinned yespower + canonical header vectors;
- custom genesis and ASERT/subsidy gates;
- three-node sync/reorg/invalid block rejection;
- wallet restart persistence;
- native yespower mining;
- CRAK-014 two-worker Stratum mining;
- CRAK-015 SQLite accounting across a pool-process restart;
- proportional/PPLNS reward allocation and satoshi conservation;
- worker hashrate/stat reporting;
- installed-package pool + ledger/payout operations paths;
- CRAK-020 end-to-end regtest payout state machine;
- CRAK-022 byte-identical deterministic archive packaging;
- CRAK-023 native ARM64 package/runtime operation;
- CRAK-024 two-builder Linux x86_64 binary and release-archive equality.

Passing these gates still does not make the project mainnet-ready. Independent public testnet operation, sustained mining/reorg tests, release signing/key custody, production pool authentication/TLS/rate limiting, broader third-party miner interoperability and external security/code review remain required.
