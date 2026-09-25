# Crakbit patch series

Crakbit is maintained as a reviewed delta from a pinned Bitcoin-derived engineering base.

Planned order:

1. lock the base source to an exact commit SHA;
2. preserve all inherited MIT/BSD notices;
3. rename daemon/CLI/config/data-directory branding to Crakbit;
4. remove inherited founder reserve, vesting and spendable-genesis consensus changes;
5. remove inherited treasury/dev-fee validation, RPC and pool payout assumptions;
6. set 21M `MAX_MONEY`, 5 CRAK subsidy, 2.1M halving interval and 100-block maturity;
7. vendor/pin Openwall yespower and wire it into the separate PoW-hash path;
8. keep SHA256d as the block ID and yespower as the target-comparison hash;
9. retain DGW v3 but retune/test for a 60-second target;
10. replace all legacy network magic, ports, address prefixes, seeds and genesis data;
11. convert reference miner and pool hashing to yespower;
12. generate Crakbit testnet genesis and commit deterministic vectors;
13. run multi-node, reorg, wallet, pool and long-running mining tests;
14. only after those gates, create separate mainnet parameters and genesis.

No production build may silently fall back to SHA256d proof of work, retain a legacy PoW validation path, or accept a legacy genesis/network identity.
