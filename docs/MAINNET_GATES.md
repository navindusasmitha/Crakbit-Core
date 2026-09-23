# Crakbit mainnet launch gates

Mainnet must not be enabled by simply changing a command-line flag. The following gates are mandatory before a mainnet genesis is frozen.

## Consensus and supply

- Exact subsidy schedule independently recomputed from base units.
- Genesis premine remains zero unless a public hard-fork-level specification change is made before genesis.
- Treasury is proven to be carved from subsidy and never added on top.
- Boundary tests cover heights 0, 1, 400000, 400001, every halving boundary, terminal emission and negative/overflow inputs.
- `MoneyRange`, coinbase-value validation and treasury-output validation are checked together.

## Proof of work

- RandomX implementation pinned by commit/tag and its upstream vectors pass.
- Cross-platform PoW vectors pass on Linux and Windows.
- Epoch bootstrap, lag and rollover vectors are fixed and published.
- DGW vectors cover fast blocks, slow blocks, timestamp clamping and the first 24 blocks.
- Header-sync behavior is tested with per-block retargeting and non-zero minimum chainwork.

## Network identity

- Unique mainnet message-start bytes.
- Unique P2P/RPC ports with RPC not colliding with Core's onion bind convention.
- Mainnet Base58/Bech32 prefixes fixed and tested.
- Mainnet BIP44 coin type registered or a documented final value frozen before users create valuable wallets.
- Independent DNS/fixed seeds deployed with operator consent.

## Genesis

- Final timestamp phrase published before mining.
- Final source commit tagged before genesis mining.
- Mainnet genesis mined from that exact source.
- nTime, nBits, nNonce, merkle root, block hash and RandomX PoW hash published.
- Multiple independent machines reproduce and accept the same genesis.

## Treasury custody

- Mainnet treasury key generated offline.
- Public address committed before genesis / first treasury-paying block.
- Backup and recovery procedure rehearsed.
- No private key appears in Git, CI, chat logs, build logs or cloud secrets unless deliberately used by an offline signing workflow.

## Node / wallet / miner / pool

- Fresh sync from genesis passes.
- Reindex passes.
- Wallet create/backup/restore passes.
- Test transaction and RBF/CPFP behavior reviewed.
- Solo mining and pool mining both find accepted blocks.
- Pool payout accounting survives restarts and duplicate/maturation edge cases.
- Miner rejects stale jobs without corrupting accounting.
- Explorer agrees with at least two independent nodes.

## Release engineering

- Reproducible source manifest.
- Release SHA256SUMS.
- Offline release-signing key and detached signatures.
- Linux and Windows release binaries built from the tagged source.
- CPU instruction baseline check prevents builder-specific binaries.
- Dependency/license inventory published.

## Security

- Static review of every Crakbit-specific consensus diff.
- Fuzz/functional tests for parsing and consensus boundaries.
- External review of consensus, RandomX integration and pool money path.
- Responsible-disclosure address published.
- No known critical/high issue remains open.
- Testnet has run long enough to exercise multiple RandomX epochs, difficulty shocks, node restarts, wallet restores and reorg monitoring.

## Mainnet enablement rule

The testnet branch must keep mainnet marked unsupported. Enabling mainnet requires a dedicated reviewed commit that freezes all mainnet constants and genesis values. It must never be enabled by CI environment variables or runtime configuration.
