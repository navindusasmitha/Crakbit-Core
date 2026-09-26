# Patch series

Crakbit is maintained as a small reviewed transformation series on top of the pinned Bitcoin Core release.

Current order/status:

1. ✅ pin Openwall yespower source revision and retain upstream notices;
2. ✅ wire yespower into the Bitcoin Core CMake build;
3. ✅ implement the Crakbit block-header identity hash using fixed yespower parameters;
4. ✅ add deterministic yespower/header test vectors;
5. ✅ replace Bitcoin testnet/regtest network identity with Crakbit values;
6. ✅ generate and lock Crakbit zero-reward testnet/regtest genesis blocks;
7. ✅ implement and test CRAK-007 ASERT difficulty;
8. ✅ implement and test CRAK-008 subsidy/halving/coinbase-maturity monetary rules;
9. ⏳ add CPU miner and multi-node functional/reorg tests;
10. ⏳ only after testnet gates pass, create separate mainnet parameters and genesis.

No patch in this series may silently fall back to SHA256d PoW, restore the Bitcoin 50 BTC subsidy formula, introduce a premine, or enable mainnet before the documented launch gates pass.
