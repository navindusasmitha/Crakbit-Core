# Crakbit Core

Crakbit Core is a Bitcoin-style UTXO Proof-of-Work blockchain focused on low-resource CPU mining.

## Source strategy

Crakbit now uses the **WAM Coin codebase as the architectural upstream** instead of rebuilding the same Bitcoin-fork plumbing from scratch. WAM already provides a patch-based Bitcoin Core fork layout, separate block-ID/PoW handling, per-block difficulty retargeting, miner/pool/explorer structure, and deployment tooling.

Crakbit does **not** inherit WAM's monetary policy or network identity.

Upstreams:

- WAM Coin source: `https://gitlab.com/WAMCoin/wam-coin.git`, target release `v0.1.9`
- WAM's inherited Bitcoin base: Bitcoin Core v28.1
- PoW library: Openwall yespower, pinned separately

## Crakbit consensus target

- Name: **Crakbit**
- Ticker: **CRAK**
- Model: Bitcoin-style UTXO
- PoW: **yespower 1.0**, `N=2048`, `r=8`
- Block ID: Bitcoin-style **SHA256d** of the 80-byte header
- PoW comparison hash: **yespower** over the same 80-byte header
- Difficulty: **DarkGravityWave v3**, retarget every block
- Target block interval: **60 seconds**
- Initial subsidy: **5 CRAK**
- Halving interval: **2,100,000 blocks**
- Intended maximum issuance: **21,000,000 CRAK**
- Coinbase maturity: **100 blocks**
- Premine/founder reserve: **0**
- Consensus treasury/dev fee: **0**
- Decimals: **8**

The geometric emission target is `5 × 2,100,000 × 2 = 21,000,000 CRAK`, before final-unit truncation at late halvings.

## Network separation

Crakbit must never reuse WAM mainnet/testnet identity values. The engineering parameters reserve separate Crakbit message-start bytes, ports and address prefixes. Mainnet remains disabled and no mainnet genesis is committed.

Current testnet identity target:

- message start: `43 52 41 4b` (`CRAK`)
- P2P: `17771`
- RPC: `17772`
- P2PKH version: `28` (stable `C...` addresses)
- P2SH version: `87` (stable `c...` addresses)
- Bech32 HRP: `crak`

## Bootstrap the WAM-derived working tree

```bash
./scripts/bootstrap.sh
```

The script fetches the requested WAM release and the exact yespower commit, verifies the expected WAM repository layout, and creates `.work/crakbit-source` as the disposable migration working tree.

Then run:

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-address-prefixes.py
```

## Status

This repository is **not mainnet-ready**. The WAM-derived migration plan is committed, but the consensus patch must still be applied and compiled against the actual WAM source checkout before a Crakbit testnet genesis is mined.

No mainnet launch is allowed until deterministic source pinning, yespower vectors, supply tests, DGW3 tests, genesis tests, wallet tests, reorg tests and sustained multi-node testnet operation pass.

## License

Crakbit project files are MIT licensed. WAM Coin and Bitcoin Core license/copyright notices must be retained for inherited code. Openwall yespower source must retain its upstream BSD-style notices when vendored or distributed.
