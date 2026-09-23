# WAM engineering reference used by Crakbit Testnet

Crakbit Core uses a pinned snapshot of the MIT-licensed WAM Coin repository as an **engineering reference and compatibility layer** for the first testnet. Crakbit is a separate network and must never share WAM genesis data, message magic, discovery peers, addresses, wallet identity or monetary policy.

The exact WAM commit is recorded in `SOURCE_LOCK.json`.

## Patterns retained for testnet

The first Crakbit testnet intentionally retains these proven design patterns from the pinned reference:

- Bitcoin Core-derived UTXO, script, P2P and wallet implementation;
- RandomX proof-of-work integration;
- DarkGravityWave v3 per-block retargeting;
- deterministic RandomX epoch/seed-lag handling;
- a single source-of-truth header for monetary constants;
- treasury enforcement as a consensus rule where the treasury share is carved **from** subsidy, not minted in addition to it;
- independent node, miner, Stratum pool and explorer components;
- reproducible source materialization from pinned upstream versions;
- genesis-generation tooling and explicit genesis verification;
- accounting and API regression tests for the mining pool;
- release/build verification as a security property.

## Crakbit-specific replacements

Crakbit Testnet v0.1 replaces the reference network identity and economics with independent values:

- currency: CBIT;
- initial subsidy: 10 CBIT;
- halving interval: 1,051,200 blocks;
- genesis premine: 0 CBIT;
- treasury: 5% of subsidy for heights 1..400,000;
- target spacing: 120 seconds;
- testnet RandomX epoch: 256 blocks;
- testnet RandomX seed lag: 16 blocks;
- P2P: 29111;
- RPC: 29110, localhost-only by default;
- bech32 HRP: `tcb`;
- independent message-start bytes;
- independent genesis phrase and RandomX bootstrap key;
- no WAM DNS seeds or fixed seeds.

## What is *not* considered final for mainnet

The testnet compatibility layer currently inherits the WAM reference's Bitcoin Core v28.1 patch base. Bitcoin Core 28.x is end-of-life as of the Bitcoin Core 31.x lifecycle, so Crakbit mainnet must not launch solely because this testnet works. A mainnet code freeze requires either a reviewed rebase onto a maintained Bitcoin Core release or a documented independent security review of the retained base.

Likewise, the testnet branch must not reuse its placeholder mainnet genesis, testnet treasury burn destination, temporary discovery configuration or provisional wallet/BIP44 decisions for mainnet.

## Rule for future imports

Do not blindly copy new WAM commits. Any future reference change must be pinned by commit, reviewed as a source update, run through the full Crakbit transform, and pass monetary, genesis, node, RandomX, pool and explorer CI before it can replace the current lock.