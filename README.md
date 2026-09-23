# Crakbit Core

Crakbit Core is the reference implementation workspace for the **CBIT proof-of-work blockchain**.

> Status: **pre-mainnet / Testnet v0.1 engineering**. Testnet CBIT has no monetary value. Do not use this repository for real-value mainnet funds until the documented mainnet launch gates are completed and independently reviewed.

## Testnet v0.1

The testnet branch builds a complete development-network stack from pinned, reviewable source inputs:

- full node + CLI + wallet utilities;
- RandomX proof of work;
- DarkGravityWave v3 per-block difficulty adjustment;
- CPU miner;
- Stratum mining pool;
- block explorer;
- deterministic testnet/regtest genesis generation;
- monetary-policy and pool-accounting tests;
- reproducible build/source identity records;
- public-node deployment tooling.

A successful GitHub Actions run publishes both Linux binaries and a **full transformed source archive** for the exact Crakbit testnet commit.

## Current consensus target

| Parameter | Testnet v0.1 |
|---|---:|
| Currency | Crakbit Coin (CBIT) |
| Decimals | 8 |
| Consensus | Proof of Work |
| PoW | RandomX v1 family |
| Block target | 120 seconds |
| Difficulty | DGW v3, every block, 24-block window |
| Initial subsidy | 10 CBIT |
| Halving interval | 1,051,200 blocks |
| Genesis premine | 0 CBIT |
| Treasury | 5% of subsidy, heights 1..400,000 |
| Scheduled subsidy emission | 21,023,999.86334400 CBIT |
| Testnet P2P | TCP 29111 |
| Testnet RPC | TCP 29110, localhost-only by default |
| Testnet bech32 HRP | `tcb` |
| Testnet RandomX epoch | 256 blocks |
| Testnet RandomX seed lag | 16 blocks |

The treasury share is carved from the configured block subsidy. It does **not** mint additional CBIT. At height 1 the 10 CBIT subsidy is split into 9.5 CBIT for the miner and 0.5 CBIT for the testnet treasury destination.

## Source model

Crakbit Testnet v0.1 uses a pinned MIT-licensed WAM Coin snapshot as an engineering reference/compatibility layer, then applies independent Crakbit network and monetary parameters. The materialized node source is ultimately Bitcoin Core-derived. Crakbit does not connect to WAM: testnet genesis data, RandomX domain key, message magic, ports, address namespace and discovery configuration are independent.

The exact dependency lock is in `SOURCE_LOCK.json`. The current testnet deliberately remains on the reference layer's Bitcoin Core v28.1 patch base; Bitcoin Core 28.x is end-of-life, so **mainnet is blocked** until the maintained-base/review requirement in `docs/MAINNET_GATES.md` is satisfied.

## Build on Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential libtool autotools-dev automake pkg-config bsdmainutils \
  cmake git python3 libevent-dev libboost-dev libboost-system-dev \
  libboost-filesystem-dev libboost-test-dev libssl-dev libsqlite3-dev \
  nodejs npm

python3 tests/test_policy.py
CRAKBIT_JOBS=2 CRAKBIT_GENESIS_THREADS=2 bash scripts/materialize.sh
CRAKBIT_JOBS=2 bash scripts/build-testnet.sh
```

Then initialize and start an isolated testnet node:

```bash
bash scripts/testnet.sh init
bash scripts/testnet.sh start
bash scripts/testnet.sh status
```

## Public testnet deployment

After the complete CI pipeline is green, follow `docs/PUBLIC_TESTNET_DEPLOY.md`. The hardened Ubuntu installer is:

```bash
sudo bash deploy/install-testnet-node.sh
```

Only P2P TCP 29111 should be public. Do not expose RPC 29110 to the Internet.

## Documentation

- `docs/ARCHITECTURE.md` — architecture and consensus layering
- `docs/TESTNET.md` — build/use instructions
- `docs/PUBLIC_TESTNET_DEPLOY.md` — two-node public testnet runbook
- `docs/WAM_REFERENCE.md` — what is learned/inherited from the pinned WAM reference and what Crakbit replaces
- `docs/MAINNET_GATES.md` — mandatory mainnet blockers
- `SECURITY.md` — responsible disclosure and consensus-security priorities

## Mainnet

Mainnet is a separate code-freeze milestone. Its genesis block, treasury custody, discovery peers, release signing, minimum-chainwork/checkpoint policy and maintained upstream base are intentionally **not** inherited from the testnet placeholder configuration.
