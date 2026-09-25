# Crakbit Core

Crakbit Core is an independent Bitcoin-style UTXO Proof-of-Work blockchain focused on low-resource CPU mining.

## Crakbit identity

All runtime, wallet, network, miner, pool, explorer, package and user-facing naming is **Crakbit / CRAK**. Historical source provenance is kept only in source-lock/license metadata for reproducibility and attribution.

## Consensus target

- Name: **Crakbit**
- Ticker: **CRAK**
- Model: Bitcoin-style UTXO
- PoW: **yespower 1.0**, `N=2048`, `r=8`
- Block ID: **SHA256d** of the 80-byte header
- PoW comparison hash: **yespower** over the same 80-byte header
- Difficulty: **DarkGravityWave v3**, every block
- Target block interval: **60 seconds**
- Initial subsidy: **5 CRAK**
- Halving interval: **2,100,000 blocks**
- Intended maximum issuance: **21,000,000 CRAK**
- Exact v0.1 terminal issuance: **20,999,999.72700000 CRAK**
- Coinbase maturity: **100 blocks**
- Premine: **0**
- Treasury/dev fee: **0**
- Decimals: **8**

## Testnet identity

- message start: `43 52 41 4b` (`CRAK`)
- P2P port: `17771`
- RPC port: `17772`
- P2PKH version: `28`
- P2SH version: `87`
- secret-key version: `197`
- Bech32 HRP: `crak`

Mainnet identity and genesis remain unset until the testnet gates pass.

## Engineering layout

Crakbit-owned rules live under `src/crakbit/`. The migration helper applies a reviewed `CRAK-*` patch series to a pinned engineering base instead of silently editing an untracked source tree.

Useful checks:

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-address-prefixes.py
python3 scripts/verify_supply.py --schedule
python3 genesis/test_serialization.py
python3 scripts/patch_upstream.py --list
```

Prepare the pinned working tree:

```bash
./install.sh --prepare
```

Run local checks only:

```bash
./install.sh --check
```

## Status

This repository is **not mainnet-ready**. Full daemon builds stay gated until the Crakbit consensus transformations, yespower validation path, DGW3 tuning, network identity replacement, custom genesis and multi-node tests are implemented and verified.

See `docs/LAUNCH_CHECKLIST.md`.

## License and provenance

Crakbit project files are MIT licensed. Third-party source origins and exact commit locks remain recorded in `SOURCE_LOCK.json`; inherited copyright/license notices must remain intact. Openwall yespower retains its upstream BSD-style notices.
