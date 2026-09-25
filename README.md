# Crakbit Core

Crakbit Core is a Bitcoin-style UTXO Proof-of-Work blockchain project focused on CPU mining.

## v0.1 direction

- Upstream base: **Bitcoin Core v31.1** (pinned commit)
- PoW library: **Openwall yespower** (pinned commit)
- PoW profile: **YESPOWER_1_0, N=2048, r=8**
- Block-header identity / PoW hash: **yespower over the canonical 80-byte header**
- Target block interval: **60 seconds**
- Initial block subsidy target: **5 CRAK**
- Halving interval target: **2,100,000 blocks**
- Intended maximum issuance: **21,000,000 CRAK**
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

## Important status

This repository is still a **v0.1 engineering/testnet project**. It is **not mainnet-ready** and does not claim production safety. Mainnet, Bitcoin testnet3 compatibility, and signet remain disabled while monetary consensus, full node/wallet builds, reorg/invalid-chain tests, multi-node mining, and sustained public testnet gates are completed.

## Bootstrap pinned upstream sources

```bash
./scripts/bootstrap.sh
```

This creates `.work/bitcoin` and `.work/yespower` at the exact commits recorded in `SOURCE_LOCK.json`.

Materialize the reviewed Crakbit consensus tree through CRAK-007:

```bash
bash scripts/materialize-locked.sh
```

Verify locked source/network/genesis configuration and independent ASERT vectors:

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
```

## Repository layout

```text
Crakbit-Core/
├── consensus/params.json
├── docs/
│   ├── BUILD.md
│   └── CONSENSUS.md
├── scripts/
│   ├── bootstrap.sh
│   ├── materialize-locked.sh
│   ├── apply-asert.py
│   ├── verify-asert-vectors.py
│   └── verify-lock.py
├── src/crakbit/
│   ├── asert.cpp
│   └── asert.h
├── tests/
│   ├── asert_vectors.json
│   ├── genesis_vectors.json
│   └── yespower_vectors.json
├── SOURCE_LOCK.json
└── README.md
```

## Safety rule

No mainnet genesis block will be finalized until deterministic builds, PoW/difficulty vectors, monetary consensus tests, reorg and invalid-chain tests, wallet tests, and sustained multi-node public testnet mining have passed review.

## License

Crakbit project files are MIT licensed. Upstream Bitcoin Core remains under its own MIT notices. yespower source must retain its upstream BSD-style notices when vendored or distributed. CRAK-007 ASERT is adapted from the MIT-licensed Bitcoin Cash/Bitcoin ABC ASERT reference design with Crakbit-specific wide-intermediate handling for its easy CPU-test target.
