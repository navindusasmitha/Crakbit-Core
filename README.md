# Crakbit Core

Crakbit Core is a Bitcoin-style UTXO Proof-of-Work blockchain project focused on CPU mining.

## v0.1 consensus profile

- Upstream base: **Bitcoin Core v31.1** (pinned commit)
- PoW library: **Openwall yespower** (pinned commit)
- PoW profile: **YESPOWER_1_0, N=2048, r=8**
- Block-header identity / PoW hash: **yespower over the canonical 80-byte header**
- Target block interval: **60 seconds**
- Initial block subsidy: **5 CRAK**
- Halving interval: **2,100,000 blocks**
- Nominal geometric cap: **21,000,000 CRAK**
- Exact integer-rounded subsidy total: **20,999,999.72700000 CRAK**
- Coinbase maturity: **100 blocks**
- Testnet difficulty: **ASERT**, 2-hour (7,200 second) half-life
- ASERT anchor: **genesis conceptual parent one target-spacing before genesis**
- Regtest difficulty: **no retargeting** for deterministic local testing
- Premine: **0**

## Implemented consensus/network milestones

- CRAK-004: pinned yespower build integration
- CRAK-005: yespower block-header identity hash + deterministic vector
- CRAK-006: isolated Crakbit testnet/regtest identity + zero-reward custom genesis blocks
- CRAK-007: integer-only ASERT testnet difficulty + frozen Python/C++ vectors
- CRAK-008: 5 CRAK subsidy, 2,100,000-block halving, 100-block maturity, zero premine + compiled boundary vectors

## Important status

This repository is still a **v0.1 engineering/testnet project**. It is **not mainnet-ready** and does not claim production safety. Mainnet, Bitcoin testnet3 compatibility, and signet remain disabled while full node/wallet builds, reorg and invalid-chain tests, CPU miner integration, multi-node mining, and sustained public testnet gates are completed.

## Bootstrap pinned upstream sources

```bash
./scripts/bootstrap.sh
```

This creates `.work/bitcoin` and `.work/yespower` at the exact commits recorded in `SOURCE_LOCK.json`.

Materialize the reviewed Crakbit consensus tree through CRAK-008:

```bash
bash scripts/materialize-locked.sh
```

Verify locked source/network/genesis/monetary configuration and independent ASERT vectors:

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
```

CI additionally compiles and executes the yespower, block-header, genesis, ASERT, and subsidy probes against the materialized Bitcoin Core tree.

## Repository layout

```text
Crakbit-Core/
├── consensus/params.json
├── docs/
│   ├── BUILD.md
│   └── CONSENSUS.md
├── patches/
│   └── README.md
├── scripts/
│   ├── bootstrap.sh
│   ├── materialize-locked.sh
│   ├── apply-asert.py
│   ├── apply-monetary.py
│   ├── verify-asert-vectors.py
│   ├── check-asert-binary.py
│   ├── check-subsidy-binary.py
│   └── verify-lock.py
├── src/crakbit/
│   ├── asert.cpp
│   ├── asert.h
│   ├── subsidy.cpp
│   └── subsidy.h
├── tests/
│   ├── asert_vectors.json
│   ├── genesis_vectors.json
│   ├── subsidy_vectors.json
│   └── yespower_vectors.json
├── SOURCE_LOCK.json
└── README.md
```

## Monetary rounding

Crakbit keeps Bitcoin-style integer right-shift halvings. Starting from 500,000,000 satoshis per block, the final non-zero subsidy era pays 1 satoshi per block and subsidy becomes zero at height 60,900,000. Because every halving truncates integer satoshis, the exact subsidy sum is 2,099,999,972,700,000 satoshis (20,999,999.72700000 CRAK), slightly below the nominal 21 million geometric limit.

The custom testnet and regtest genesis blocks have a **zero CRAK reward**, so they create no premine.

## Safety rule

No mainnet genesis block will be finalized until deterministic builds, PoW/difficulty/monetary vectors, reorg and invalid-chain tests, wallet tests, and sustained multi-node public testnet mining have passed review.

## License

Crakbit project files are MIT licensed. Upstream Bitcoin Core remains under its own MIT notices. yespower source must retain its upstream BSD-style notices when vendored or distributed. CRAK-007 ASERT is adapted from the MIT-licensed Bitcoin Cash/Bitcoin ABC ASERT reference design with Crakbit-specific wide-intermediate handling for its easy CPU-test target.
