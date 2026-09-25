# Crakbit patch series

Crakbit is maintained as a reviewed delta from the WAM Coin fork architecture.

Planned order:

1. lock WAM `v0.1.9` to an exact commit SHA after checkout;
2. preserve all inherited MIT/BSD notices;
3. rename daemon/CLI/config/data-directory branding;
4. remove WAM founder reserve, vesting and spendable-genesis consensus changes;
5. remove WAM treasury/dev-fee validation, RPC and pool payout assumptions;
6. set 21M `MAX_MONEY`, 5 CRAK subsidy, 2.1M halving interval and 100-block maturity;
7. vendor/pin Openwall yespower and wire it into WAM's separate PoW-hash path;
8. keep SHA256d as the block ID and yespower as the target-comparison hash;
9. retain DGW v3 but retune/test for a 60-second target;
10. replace all WAM network magic, ports, address prefixes, seeds and genesis data;
11. convert reference miner and pool native hashing from RandomX to yespower;
12. generate Crakbit testnet genesis and commit deterministic vectors;
13. run multi-node, reorg, wallet, pool and long-running mining tests;
14. only after those gates, create separate mainnet parameters and genesis.

No production build may silently fall back to SHA256d proof of work, retain a RandomX validation path, or accept a WAM genesis/network identity.
