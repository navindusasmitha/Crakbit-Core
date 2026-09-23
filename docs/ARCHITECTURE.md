# Crakbit Core architecture

## Goal

Crakbit Core is a Bitcoin-Core-derived UTXO blockchain with RandomX proof of work. The first public network is a testnet. Mainnet is intentionally blocked until the launch gates in `MAINNET_GATES.md` are complete.

## Source model

Crakbit does not reimplement Bitcoin networking, script, UTXO, wallet and P2P code from scratch. A pinned, MIT-licensed WAM Coin snapshot is used as the engineering reference layer because it already integrates RandomX, per-block DarkGravityWave difficulty, a Stratum pool, an explorer, monetary tests and release/security tooling on top of a pinned Bitcoin Core tree.

The exact reference commit is recorded in `SOURCE_LOCK.json`. `scripts/materialize.sh` clones that exact commit, applies the Crakbit overlay and refuses to continue if the fetched commit differs.

This keeps the Crakbit repository small enough to audit while still producing a complete build tree.

## Consensus policy for testnet-v0.1

- Unit: 1 CBIT = 100,000,000 base units.
- Target block spacing: 120 seconds.
- Proof of work: RandomX.
- Difficulty: DarkGravityWave v3, retarget every block, 24-block window, 3x clamp.
- Genesis premine: 0 CBIT.
- Initial subsidy: 10 CBIT from block 1.
- Halving interval: 1,051,200 blocks.
- Maximum halvings: 30; integer shifting terminates subsidy.
- Scheduled subsidy emission: 21,023,999.86334400 CBIT.
- Treasury: 5% of the block subsidy for heights 1..400,000 inclusive, carved out of the subsidy. Transaction fees remain with miners.
- Coinbase maturity: 100 blocks.
- SegWit/CSV/CLTV/DERSIG/BIP34 family: active from the beginning of the new chain, subject to the implementation inherited from the pinned base.
- Chain selection: greatest cumulative valid proof of work.

## RandomX seed schedule

Production intent is 2,048-block epochs with a 64-block lag. Testnet deliberately uses 256-block epochs and a 16-block lag so epoch-boundary behavior is exercised frequently.

Epoch zero uses a fixed domain-separated bootstrap key. Later epochs derive their seed from buried accepted-chain block data. The same constants must be used by the node, miner and pool.

## Testnet identity

Testnet uses independent message magic, ports, genesis phrase/hash, and bech32 HRP. It intentionally has no DNS seed at initial launch. Operators connect seed nodes with explicit `-addnode` entries until independent seeds are deployed.

## Compatibility note

During testnet-v0.1, some internal source paths and identifiers retain the WAM names because the pinned patch layer expects them. They are implementation details, not network identity. User-facing wrappers, configuration and Crakbit consensus constants are separate. A full internal rename is scheduled before mainnet code freeze, after behavior is stable.

## Security model

No proof-of-work chain can honestly guarantee immunity from majority-hash attacks. The launch plan therefore combines independent mining/pools, conservative confirmations, chain-concentration reporting, deep-reorg monitoring, minimum-chainwork updates after sufficient history exists, signed releases and an explicit security review before mainnet.
