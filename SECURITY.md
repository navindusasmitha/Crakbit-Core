# Crakbit Core security policy

Crakbit Core is currently a **testnet engineering project**. Testnet CBIT has no monetary value and testnet state may be reset while consensus work is in progress.

## Report privately

Do not publish a working consensus, wallet, pool-fund, remote-crash or key-exposure vulnerability before maintainers have had a reasonable opportunity to reproduce and fix it.

For now, open a minimal GitHub issue that contains **no exploit details** and asks for a private disclosure channel, or contact the Crakbit Society security contact already published by the project. Do not post proof-of-concept exploit code in a public issue.

A good report includes:

- affected commit and platform;
- component (`node`, `consensus`, `miner`, `pool`, `explorer`, `scripts`, release tooling);
- expected vs actual behaviour;
- exact local/testnet reproduction steps;
- security impact;
- a patch or failing regression test when available.

## Highest-priority classes

Crakbit treats these as critical design failures:

- creation of CBIT outside the configured emission schedule;
- accepting an invalid treasury amount or treasury destination;
- honest nodes disagreeing on the validity of the same block;
- bypassing proof-of-work or difficulty validation;
- deterministic RandomX seed/epoch disagreement;
- remote node crash or permanent stall from crafted network/block/transaction input;
- theft of pool balances or miner shares;
- wallet private-key or seed disclosure;
- release/build compromise that can produce binaries not matching reviewed source.

## Test only on controlled networks

Security research must use regtest, an isolated local testnet, or the public Crakbit testnet in a way that does not disrupt other participants. Do not attempt majority-hash attacks, double-spends against third parties, denial of service, credential theft, or destructive testing on systems you do not own or have explicit permission to test.

## Consensus-change discipline

Any change to supply, block subsidy, treasury rules, PoW validation, RandomX seed selection, difficulty adjustment, genesis data, message magic, address prefixes, BIP44 identity, or network ports must be reviewed as consensus/network identity work and accompanied by tests.

Mainnet is blocked until the gates in `docs/MAINNET_GATES.md` are satisfied.