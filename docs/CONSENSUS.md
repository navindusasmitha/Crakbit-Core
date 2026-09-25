# Crakbit Consensus Design v0.1

## Model

Crakbit is designed as a Bitcoin-style UTXO chain. The project intentionally reuses mature Bitcoin Core transaction, script, wallet, mempool, storage, and P2P architecture instead of implementing those systems from scratch.

## Proof of Work

Crakbit v0.1 uses Openwall yespower with:

- `YESPOWER_1_0`
- `N = 2048`
- `r = 8`
- personalization string `Crakbit-Core-v0.1`
- canonical 80-byte serialized block header as the hash input

The block-header identity hash is also the yespower PoW hash. Transaction IDs and signature hashing remain Bitcoin-derived and are not replaced with yespower.

The roughly 2 MiB-class setting is intended to keep mining practical on low-end CPUs while making the function memory-aware. It does **not** make all CPUs equal and it does **not** guarantee permanent ASIC resistance.

## Block and issuance targets

- Target spacing: 60 seconds
- Initial subsidy target: 5 CRAK
- Halving interval target: 2,100,000 blocks
- Premine: 0 CRAK
- Coinbase maturity: 100 blocks
- 8 decimal places

The target geometric issuance converges to 21,000,000 CRAK subject to integer-unit rounding. Monetary constants must be separately patched and tested in the materialized Bitcoin Core consensus code before the monetary milestone is considered complete.

## Difficulty — CRAK-007

Crakbit testnet uses deterministic integer ASERT with a **7,200 second half-life** and **60 second target spacing**.

The absolute schedule is anchored to genesis. Because genesis has no real parent, its conceptual parent is defined as one target-spacing before the genesis timestamp. This makes a perfectly scheduled chain retain the genesis target.

The calculation uses signed 16.16 fixed-point exponent arithmetic and the audited ASERT cubic approximation. Consensus code does not use floating point. Crakbit's easy CPU-test `powLimit` has less headroom than the original Bitcoin Cash reference assumptions, so the multiplication/shift intermediate is widened to 512 bits and then deterministically clamped back to the 256-bit `powLimit`.

Testnet rules:

- ASERT enabled
- special minimum-difficulty shortcut disabled
- target recomputed through `GetNextWorkRequired()`
- 7,200-second half-life
- genesis absolute anchor

Regtest keeps no-retargeting enabled for deterministic local development.

Frozen ASERT vectors cover ideal schedule, faster/slower blocks, ±half-life movement, long-height schedules, pow-limit clamping, target-floor behavior, and the real `GetNextWorkRequired()` testnet routing path. An independent Python unlimited-integer verifier is checked against the compiled C++ implementation in CI.

## Network isolation

Crakbit testnet/regtest have separate message-start bytes, P2P/RPC ports, address prefixes, Bech32 HRPs and custom zero-reward genesis blocks. Bitcoin mainnet, Bitcoin testnet3 compatibility and signet remain disabled in v0.1.

## Mainnet gates

Mainnet must remain disabled until all of the following pass:

1. deterministic source pinning and reproducible builds;
2. upstream yespower and Crakbit 80-byte block-header vectors;
3. custom genesis generation and fixed expected hashes;
4. unique network magic, ports and address prefixes;
5. ASERT deterministic vectors, overflow/underflow handling and timestamp-edge tests;
6. actual Crakbit monetary subsidy/halving consensus tests;
7. reorg and invalid-chain tests;
8. wallet send/receive/restart tests;
9. at least three independent nodes mining the same public testnet;
10. sustained testnet operation before a separate mainnet genesis is created.
