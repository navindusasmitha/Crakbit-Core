# Crakbit Core

Crakbit Core is the reference implementation workspace for the CBIT proof-of-work blockchain.

> Status: **pre-mainnet / testnet engineering**. Do not use this repository for real-value mainnet funds until the mainnet launch gates are completed and independently reviewed.

The project follows a reproducible upstream-source model: a pinned Bitcoin Core base plus a reviewed Crakbit consensus patch/overlay layer, RandomX proof-of-work integration, deterministic monetary policy, testnet tooling, and security/release checks.

## Current network target

- Currency: **Crakbit Coin (CBIT)**
- Consensus: Proof of Work
- PoW family: RandomX
- Target block spacing: 120 seconds
- Initial subsidy: 10 CBIT
- Halving interval: 1,051,200 blocks
- Premine: none
- Treasury: 5% of subsidy, heights 1 through 400,000, carved from the subsidy (not extra issuance)
- Scheduled subsidy emission: 21,023,999.86334400 CBIT

Development is performed on testnet/regtest first. Mainnet genesis, network identifiers, treasury custody, release signing, checkpoints/chainwork policy and public launch parameters remain blocked until the documented mainnet gates are satisfied.

## Sources used for engineering reference

Crakbit Core draws implementation lessons from Bitcoin Core and the MIT-licensed WAM Coin codebase, while using independent Crakbit network parameters and monetary rules.

See `docs/ARCHITECTURE.md`, `docs/TESTNET.md`, and `docs/MAINNET_GATES.md` on the development branch.
