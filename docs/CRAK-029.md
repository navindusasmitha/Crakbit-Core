# CRAK-029 — Miner/node interoperability and release rehearsal

CRAK-029 turns the existing node, miner, pool, packaging and release-trust work into one native release rehearsal that must pass on both maintained Linux architectures.

## Goal

Prove that the release package is not merely buildable: it can be installed, exercised through the maintained mining protocols, replaced by a second package revision, and restarted without losing the regtest chain, wallet or pool ledger used by the rehearsal.

The reviewed machine-readable contract is `release/INTEROP_MATRIX.json`.

## Native architecture matrix

The required CI lanes are:

- Linux x86_64 on `ubuntu-24.04`;
- Linux ARM64 on native `ubuntu-24.04-arm` hardware.

Cross-compile-only or emulated ARM results do not satisfy the ARM64 lane.

Both lanes build `crakbitd`, `crakbit-cli` and `crakminer-scan`, produce the normal deterministic Linux package, install it into a clean prefix and execute the same release-rehearsal smoke.

## Mining interoperability contract

The rehearsal covers two maintained mining boundaries.

### getblocktemplate

`crakminer-native` must obtain work from `crakbitd`, hash the canonical 80-byte header using the packaged native yespower scanner and submit a valid regtest block.

### Stratum V1 subset

The installed persistent `crakpool` must interoperate with:

1. `tests/interop_protocol_probe.py`, an independent socket/JSON-lines client that does not import Crakbit pool or miner implementation modules; and
2. the official installed `crakminer-stratum`, which must submit an accepted share and a valid regtest block.

The independent probe checks the maintained subset around `mining.subscribe`, `mining.authorize`, `mining.set_difficulty`, `mining.notify`, `mining.suggest_difficulty` and the unsupported-method error contract. The official miner then proves the actual `mining.submit` path.

This is protocol interoperability evidence, not certification of arbitrary third-party mining software.

## Release rehearsal

`tests/release_rehearsal_smoke.sh` performs the following sequence on each native architecture:

1. build `ci-rehearsal-a` from the exact checked-out source commit;
2. verify the archive SHA256 sidecar, internal `SHA256SUMS` and `BUILD-MANIFEST.json`;
3. install the package and verify the installed native binary architecture;
4. start an isolated regtest node and create a rehearsal wallet;
5. mine through the RPC helper and `crakminer-native`;
6. start the persistent pool, run the independent Stratum probe, then mine through `crakminer-stratum`;
7. record the chain tip, wallet state and pool ledger and stop all services;
8. build and install `ci-rehearsal-b` over the same prefix;
9. build and verify the CRAK-025 testnet `RELEASE-MANIFEST.json` for the second package;
10. restart with the same datadir and verify the chain tip, wallet and pool ledger survived the package replacement;
11. mine another block after the upgrade and verify the packaged CRAK-028 edge entry point still loads.

The two rehearsal version labels intentionally differ even though CI uses the same source tree. The purpose is to exercise package replacement and state compatibility, not to claim a historical binary upgrade from an older public release.

## Fail-closed integrity

`scripts/verify-interop-integrity.py` rejects weakening of the CRAK-029 architecture matrix, protocol requirements, state-preservation requirements or mainnet boundary. It also requires the rehearsal, independent protocol probe, dedicated workflow, package wiring and project-state documentation to remain present.

## Scope boundary

CRAK-029 does not:

- activate mainnet;
- claim that real CRAK-026 public nodes or CRAK-027 72-hour evidence exist;
- certify arbitrary external third-party miners;
- replace CRAK-028 public-pool TLS/auth/perimeter requirements;
- perform an external security audit;
- provision the future offline mainnet release key.

A public testnet still requires real bootstrap hosts, retained soak evidence and a real hardened pool deployment. Mainnet remains a later explicit activation milestone.
