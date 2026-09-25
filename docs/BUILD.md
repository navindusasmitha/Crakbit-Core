# Build / Development Bootstrap

## Linux prerequisites

Install Git, Python 3, CMake, a C/C++ toolchain, Ninja, and the normal Bitcoin Core build dependencies for your distribution.

## Materialize pinned upstreams

```bash
./scripts/bootstrap.sh
```

The script creates:

- `.work/bitcoin` at the exact Bitcoin Core v31.1 commit locked in `SOURCE_LOCK.json`;
- `.work/yespower` at the exact Openwall yespower commit locked in `SOURCE_LOCK.json`.

It verifies both checked-out commit SHAs before returning success.

## Current stage

v0.1 intentionally stops after deterministic source materialization. The next patch series will add yespower to Bitcoin Core's CMake targets, replace the block-header PoW hash path, create Crakbit-only chain parameters, generate genesis values, and add consensus tests.

Do not publish binaries or launch a network from this engineering-base commit as if it were mainnet-ready.
