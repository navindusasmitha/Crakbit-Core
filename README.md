# Crakbit Core

Crakbit Core is a Bitcoin-style UTXO Proof-of-Work blockchain project focused on CPU mining.

## v0.1 direction

- Upstream base: **Bitcoin Core v31.1** (pinned commit)
- PoW library: **Openwall yespower** (pinned commit)
- PoW profile: **YESPOWER_1_0, N=2048, r=8**
- Target block interval: **60 seconds**
- Initial block subsidy: **5 CRAK**
- Halving interval: **2,100,000 blocks**
- Intended maximum issuance: **21,000,000 CRAK**
- Coinbase maturity: **100 blocks**
- Difficulty design: **ASERT-style**, 2 hour half-life (not yet merged into consensus code)
- Premine: **0**

## Important status

This repository is currently the clean **v0.1 engineering base**. It is **not mainnet-ready** and does not claim production safety yet. Mainnet remains disabled until the yespower integration, custom chain parameters, genesis block, difficulty algorithm, tests, and multi-node testnet gates are implemented and reviewed.

## Bootstrap pinned upstream sources

```bash
./scripts/bootstrap.sh
```

This creates `.work/bitcoin` and `.work/yespower` at the exact commits recorded in `SOURCE_LOCK.json`.

Verify the locked consensus/source configuration:

```bash
python3 scripts/verify-lock.py
```

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
│   └── verify-lock.py
├── SOURCE_LOCK.json
└── README.md
```

## Safety rule

No mainnet genesis block will be finalized until a public testnet passes deterministic build, PoW test vectors, difficulty/reorg tests, wallet tests, and sustained multi-node mining tests.

## License

Crakbit project files are MIT licensed. Upstream Bitcoin Core remains under its own MIT notices. yespower source must retain its upstream BSD-style notices when vendored or distributed.
