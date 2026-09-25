# Build / Development Bootstrap

## Linux prerequisites

Install Git, Python 3, CMake, a C/C++ toolchain, Ninja, and the normal Bitcoin Core build dependencies for your distribution.

## Materialize pinned sources

```bash
./scripts/bootstrap.sh
```

The script creates:

- `.work/base-upstream` at the exact engineering-base commit locked in `SOURCE_LOCK.json`;
- `.work/yespower` at the exact Openwall yespower commit locked in `SOURCE_LOCK.json`;
- `.work/crakbit-source` as the disposable Crakbit migration tree.

It verifies checked-out commit SHAs before returning success.

## Preflight

```bash
./install.sh --check
```

or prepare and stage the overlay with:

```bash
./install.sh --prepare
```

## Current stage

The current patch series stages Crakbit-owned constants and guardrails. Full daemon compilation stays gated until the reviewed `CRAK-001..CRAK-009` transformations are applied and covered by consensus tests.

Do not publish binaries or launch a mainnet network from this engineering-stage tree.
