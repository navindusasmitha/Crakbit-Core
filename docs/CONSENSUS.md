# Crakbit Consensus Design v0.1

## Model

Crakbit is designed as a Bitcoin-style UTXO chain. The project intentionally reuses mature Bitcoin Core transaction, script, wallet, mempool, storage, and P2P architecture instead of implementing those systems from scratch.

## Proof of Work

The target PoW is Openwall yespower using:

- `YESPOWER_1_0`
- `N = 2048`
- `r = 8`
- personalization string `Crakbit-Core-v0.1`

The 2 MiB-class setting is chosen to keep mining practical on low-end CPUs while still making the function memory-aware. It does **not** make all CPUs equal and it does **not** guarantee permanent ASIC resistance.

## Block and issuance targets

- Target spacing: 60 seconds
- Initial subsidy: 5 CRAK
- Halving interval: 2,100,000 blocks
- Premine: 0 CRAK
- Coinbase maturity: 100 blocks
- 8 decimal places

With an exact geometric halving schedule starting at 5 CRAK for 2,100,000 blocks, the intended issuance converges to 21,000,000 CRAK, subject to integer-unit rounding rules in the final implementation.

## Difficulty

The intended difficulty controller is ASERT-style with a 7,200 second half-life. This is a specification target only until test vectors are committed and the implementation is reviewed.

## v0.1 implementation rule

For the first integration, Crakbit will prefer the lower-risk architecture where the block-header identity hash is the same yespower hash used by PoW. A separate SHA256d block ID plus yespower PoW hash would require wider Bitcoin Core block-index changes and is deferred unless later benchmarks justify that complexity.

Transaction IDs and signature hashing remain Bitcoin-derived and are not replaced with yespower.

## Mainnet gates

Mainnet must remain disabled until all of the following pass:

1. deterministic source pinning and reproducible builds;
2. upstream yespower test vectors;
3. Crakbit 80-byte block-header PoW vectors;
4. custom genesis generation and fixed expected hash;
5. unique network magic, ports and address prefixes;
6. difficulty overflow/underflow and timestamp tests;
7. reorg and invalid-chain tests;
8. wallet send/receive/restart tests;
9. at least three independent nodes mining the same public testnet;
10. sustained testnet operation before a separate mainnet genesis is created.
