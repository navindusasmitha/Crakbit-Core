# CRAK-023 native ARM64 runtime validation

CRAK-023 validates the current Crakbit Core Linux engineering package on native ARM64 hardware.

The goal is stronger than merely naming an archive `arm64`: the node, CLI, yespower scanner, wallet flow, native miner, persistent pool, Stratum worker and payout/operations entry points must actually execute on an ARM64 GitHub-hosted runner.

This milestone remains a testnet/regtest engineering gate. It does not enable mainnet or claim production readiness.

## Native runner

The dedicated workflow uses GitHub's native Linux ARM64 runner label:

`ubuntu-24.04-arm`

The job fails immediately unless `uname -m` reports `aarch64`.

No qemu/x86 emulation is used for the runtime proof.

## Build validation

The workflow:

1. fetches the exact pinned Bitcoin Core and yespower sources;
2. materializes the locked Crakbit source tree;
3. configures a wallet-enabled node/CLI build;
4. builds `crakbitd` and `crakbit-cli` natively on ARM64;
5. builds `crakminer-scan` natively from the pinned yespower source;
6. verifies all three native binaries are ARM64 ELF executables.

## Package and install validation

`tests/arm64_runtime_smoke.sh` then builds the normal Linux package on the ARM runner and requires an archive named:

`crakbit-core-<version>-linux-arm64.tar.gz`

The smoke verifies:

- archive SHA256 sidecar;
- internal `SHA256SUMS`;
- CRAK-022 `BUILD-MANIFEST.json` reports `platform=linux` and `arch=arm64`;
- mainnet remains disabled in the manifest;
- the complete packaged command set installs successfully;
- installed native binaries are still ARM64 ELF executables.

## Runtime proof

The installed package is exercised on isolated regtest:

- start `crakbitd` through `crakbit-start`;
- create a wallet with `crakbit-cli`;
- mine one block through the packaged RPC mining helper;
- mine another block through `crakminer-native`, exercising the native yespower scanner;
- start the persistent `crakpool` accounting pool;
- connect a packaged `crakminer-stratum` worker and mine a pool block;
- verify the real SQLite accounting ledger reports one 5 CRAK pending block reward;
- register an ARM64 worker payout address through `crakpool-payout`;
- load the real ledger through `crakpool-payops`;
- load the CRAK-017/018 `crakpool-paytx` and `crakpool-payguard` entry points without signing or broadcasting.

## CI

The dedicated workflow is:

`.github/workflows/verify-arm64.yml`

It is pull-request driven for source/build/runtime changes and push-triggered only on `main`, avoiding duplicate feature-branch builds.

## Scope boundary

CRAK-023 proves native ARM64 build, package, install and runtime behavior on the GitHub-hosted Ubuntu 24.04 ARM64 environment.

It does **not** yet prove:

- compiler-level reproducibility between independent x86_64/ARM64 builders;
- every Linux distribution or ARM board;
- public-testnet uptime or peer bootstrapping;
- release signing/key custody;
- public-pool internet-facing security;
- mainnet readiness or mainnet activation.

Those remain separate milestones.
