# Build / Development Bootstrap

## Linux prerequisites

Install Git, Python 3, CMake, a C/C++ toolchain, Ninja, and the normal Bitcoin Core build dependencies for your distribution.

For the minimal CI-style verification path on Ubuntu, the project currently installs `build-essential`, `cmake`, `pkg-config`, `libevent-dev`, and `libboost-dev`.

## Fetch pinned upstreams

```bash
./scripts/bootstrap.sh
```

The script creates:

- `.work/bitcoin` at the exact Bitcoin Core v31.1 commit locked in `SOURCE_LOCK.json`;
- `.work/yespower` at the exact Openwall yespower commit locked in `SOURCE_LOCK.json`.

It verifies both checked-out commit SHAs before returning success.

## Materialize Crakbit consensus source

```bash
bash scripts/materialize-locked.sh
```

The materializer starts from the pinned Bitcoin Core tree and applies the reviewed Crakbit stages in order:

1. yespower build integration and block-header hash path;
2. Crakbit testnet/regtest identity and custom zero-reward genesis blocks;
3. CRAK-007 integer ASERT difficulty;
4. CRAK-008 monetary consensus (5 CRAK subsidy, 2,100,000-block halving, 100-block maturity, zero premine).

The resulting source tree is written to `.work/crakbit`. `.work/materialized-source.txt` records the locked upstream commits and the active Crakbit consensus profile.

## Verify repository locks

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
```

`verify-lock.py` checks source pins, yespower vectors, network separation, frozen genesis data, monetary constants, subsidy boundary vectors, and the exact integer-rounded subsidy total.

## CI compiled probes

GitHub Actions configures a minimal Bitcoin Core build and compiles/runs dedicated probes for:

- pinned yespower output;
- canonical 80-byte block-header hash;
- frozen Crakbit genesis blocks;
- CRAK-007 ASERT vectors and `GetNextWorkRequired()` routing;
- CRAK-008 subsidy boundaries, exact supply sum, and 100-block coinbase maturity.

The branch remains an engineering/testnet branch. Passing these probes does not mean the project is ready for mainnet.

## Remaining development gates

The next engineering work is full daemon/CLI/wallet build validation, local multi-node operation, CPU mining integration, reorg/invalid-chain testing, wallet send/receive/restart testing, and sustained public testnet operation. Mainnet parameters and a separate mainnet genesis remain disabled until those gates pass review.
