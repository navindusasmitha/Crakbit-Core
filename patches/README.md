# Patch series

The Crakbit fork will be maintained as a small reviewed patch series on top of the pinned Bitcoin Core release.

Planned order:

1. vendor/pin Openwall yespower sources and licenses;
2. wire yespower into the Bitcoin Core CMake build;
3. implement the Crakbit block-header hash using fixed yespower parameters;
4. add deterministic yespower/header test vectors;
5. replace Bitcoin network identity values with Crakbit testnet values;
6. generate and lock the Crakbit testnet genesis block;
7. implement and test the ASERT-style difficulty rule;
8. change subsidy/halving/coinbase-maturity consensus constants;
9. add CPU miner and multi-node functional tests;
10. only after testnet gates pass, create separate mainnet parameters and genesis.

No patch in this series may silently fall back to SHA256d PoW.
