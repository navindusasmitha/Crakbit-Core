# Crakbit Consensus Design v0.1

## Model

Crakbit is an independent Bitcoin-style UTXO chain with its own network identity and monetary policy.

## Hash separation

Crakbit keeps Bitcoin's 80-byte block header and Bitcoin-style SHA256d block identifier. The proof-of-work value checked against `nBits` is a separate yespower hash over the serialized 80-byte header. Transaction IDs and signature hashing remain Bitcoin-derived.

## Proof of Work

- `YESPOWER_1_0`
- `N = 2048`
- `r = 8`
- personalization: `Crakbit-Core-v0.1`

This setting targets low-resource CPUs. It does not make all CPUs equal and it does not guarantee permanent ASIC resistance.

## Emission

- Target spacing: 60 seconds
- Initial subsidy: 5 CRAK
- Halving interval: 2,100,000 blocks
- Premine: 0
- Treasury/dev fee: 0
- Coinbase maturity: 100 blocks
- 8 decimals

The ideal geometric emission is 21,000,000 CRAK. Integer base-unit halvings make the exact terminal issuance 20,999,999.72700000 CRAK.

## Difficulty

Crakbit uses a DarkGravityWave v3 structure with a 24-block window and per-block retargeting. The target spacing is 60 seconds. All constants and test vectors must be reviewed for the 60-second target before testnet is considered stable.

## Removed legacy rules

Crakbit has no founder reserve, spendable genesis allocation, mandatory treasury output or legacy PoW epoch/key machinery. Inherited versions of those rules must be removed rather than merely configured off.

## Network identity

Legacy message magic, ports, address prefixes, DNS seeds, genesis blocks and chain checkpoints are forbidden in Crakbit builds. Testnet has a separate Crakbit identity and mainnet remains unset until testnet gates pass.

## Mainnet gates

1. exact base-source commit SHA recorded;
2. all inherited licenses retained;
3. yespower reference test vectors pass;
4. Crakbit 80-byte-header PoW vectors pass;
5. supply schedule test reaches no more than the hard cap;
6. treasury/founder/premine code paths are absent from consensus validation;
7. custom testnet genesis generated and fixed;
8. DGW v3 60-second difficulty/reorg/timestamp tests pass;
9. wallet send/receive/restart tests pass;
10. at least three independent nodes sustain the same public testnet;
11. only after those gates, create separate mainnet parameters and genesis.
