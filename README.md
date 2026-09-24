# Crakbit Core — Native v0.1

Crakbit Core is the independent reference implementation of the **Crakbit Coin (CBIT)** proof-of-work blockchain.

This branch is a clean native implementation. It does not materialize, patch, transform, or depend on another blockchain project's source tree. The only consensus-engine dependency currently fetched is the official RandomX library.

> Status: **native local-dev/testnet engineering**. This is not mainnet-ready and must not hold real-value funds.

## Native v0.1 milestone

Implemented now:

- independent Crakbit block/header format;
- deterministic Crakbit-native genesis mining;
- RandomX v1.2.3 fetched directly from the official upstream repository;
- 120-second block target;
- 24-block DarkGravityWave-style target retarget with 3x clamp;
- 10 CBIT initial subsidy;
- 1,051,200-block halving interval;
- zero premine;
- 5% treasury accounting for heights 1..400,000;
- persistent local chain database;
- local CPU mining;
- chain verification on startup;
- local status, chain and balance commands.

Not implemented yet in this native milestone:

- P2P networking;
- mempool and signed transactions;
- wallet/private-key subsystem;
- JSON-RPC;
- Stratum pool;
- explorer;
- production mainnet parameters.

Those will be added on top of this native core rather than through a compatibility layer.

## Consensus constants

| Parameter | Native testnet v0.1 |
|---|---:|
| Currency | Crakbit Coin |
| Ticker | CBIT |
| Decimals | 8 |
| Proof of Work | RandomX v1.2.3 |
| Block target | 120 seconds |
| Retarget window | 24 blocks |
| Retarget clamp | 3x |
| Initial subsidy | 10 CBIT |
| Halving interval | 1,051,200 blocks |
| Premine | 0 |
| Treasury | 5% of subsidy, heights 1..400,000 |
| RandomX epoch | 256 blocks |
| RandomX seed lag | 16 blocks |

## Build on Ubuntu / WSL2

```bash
sudo apt update
sudo apt install -y build-essential cmake git libssl-dev

git clone -b native-v0.1 https://github.com/navindusasmitha/Crakbit-Core.git
cd Crakbit-Core
bash scripts/build-native.sh
```

## Run locally

```bash
./build/crakbitd init
./build/crakbitd status
./build/crakbitd mine local-miner 1
./build/crakbitd status
./build/crakbitd chain
./build/crakbitd balance local-miner
```

The default data directory is `~/.crakbit/native-testnet`. Override it with `--datadir /path`.

## Security note

Native v0.1 is an engineering network. Consensus code, serialization, target arithmetic, RandomX epoch rules, transaction validation, networking and wallet code require extensive fuzzing, cross-platform tests and independent review before any mainnet release.
