# Crakbit Core

Crakbit Core is a Bitcoin-style UTXO Proof-of-Work blockchain project focused on CPU mining.

## v0.1 consensus profile

- Upstream base: **Bitcoin Core v31.1** (pinned commit)
- PoW library: **Openwall yespower** (pinned commit)
- PoW profile: **YESPOWER_1_0, N=2048, r=8**
- Block-header identity / PoW hash: **yespower over the canonical 80-byte header**
- Target block interval: **60 seconds**
- Initial block subsidy: **5 CRAK**
- Halving interval: **2,100,000 blocks**
- Nominal geometric cap: **21,000,000 CRAK**
- Exact integer-rounded subsidy total: **20,999,999.72700000 CRAK**
- Coinbase maturity: **100 blocks**
- Testnet difficulty: **ASERT**, 2-hour (7,200 second) half-life
- ASERT anchor: **genesis conceptual parent one target-spacing before genesis**
- Regtest difficulty: **no retargeting** for deterministic local testing
- Premine: **0**

## Implemented consensus/network milestones

- CRAK-004: pinned yespower build integration
- CRAK-005: yespower block-header identity hash + deterministic vector
- CRAK-006: isolated Crakbit testnet/regtest identity + zero-reward custom genesis blocks
- CRAK-007: integer-only ASERT testnet difficulty + frozen Python/C++ vectors
- CRAK-008: 5 CRAK subsidy, 2,100,000-block halving, 100-block maturity, zero premine + compiled boundary vectors
- CRAK-009: full `crakbitd` / `crakbit-cli` build, yespower CPU mining RPC, three-node sync, competing-fork reorg, and invalid-block rejection smoke

## CRAK-009 node smoke

The current CI builds the full daemon and CLI with wallet support disabled, starts three isolated Crakbit testnet nodes, mines through the existing Bitcoin Core `generatetodescriptor` nonce loop (which uses Crakbit's yespower `block.GetHash()`), synchronizes the nodes, creates competing forks, submits a deliberately mutated block, and reconnects the partition.

The locked smoke requires:

- three peers to establish real P2P connections;
- CPU-mined blocks to propagate to all nodes;
- a malformed block to be rejected (`bad-txnmrklroot` in the current vector);
- a shorter branch to reorganize to the longer-work branch;
- all three nodes to converge on the same final height/tip.

Bitcoin testnet4 minimum-chain-work and assume-valid checkpoints are not inherited; both are zero for the fresh Crakbit testnet. Bitcoin mainnet, Bitcoin testnet3 and signet remain unavailable as user-selectable Crakbit networks.

## Important status

This repository is still a **v0.1 engineering/testnet project**. It is **not mainnet-ready** and does not claim production safety. The remaining major gates are wallet-enabled build/send/receive/restart coverage, independent public testnet nodes, longer-duration CPU mining/reorg operation, release packaging/reproducibility work, and external review.

## Bootstrap pinned upstream sources

```bash
./scripts/bootstrap.sh
```

This creates `.work/bitcoin` and `.work/yespower` at the exact commits recorded in `SOURCE_LOCK.json`.

Materialize the reviewed Crakbit consensus/node tree through CRAK-009:

```bash
bash scripts/materialize-locked.sh
```

Verify locked source/network/genesis/monetary configuration and independent ASERT vectors:

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
```

CI additionally compiles and executes the yespower, block-header, genesis, ASERT, subsidy, full-node and three-node network smoke paths against the materialized Bitcoin Core tree.

## Repository layout

```text
Crakbit-Core/
├── consensus/params.json
├── docs/
│   ├── BUILD.md
│   └── CONSENSUS.md
├── patches/
│   └── README.md
├── scripts/
│   ├── bootstrap.sh
│   ├── materialize-locked.sh
│   ├── apply-asert.py
│   ├── apply-monetary.py
│   ├── apply-node.py
│   ├── verify-asert-vectors.py
│   ├── check-asert-binary.py
│   ├── check-subsidy-binary.py
│   └── verify-lock.py
├── src/crakbit/
│   ├── asert.cpp
│   ├── asert.h
│   ├── subsidy.cpp
│   └── subsidy.h
├── tests/
│   ├── asert_vectors.json
│   ├── genesis_vectors.json
│   ├── local_multinode_smoke.sh
│   ├── subsidy_vectors.json
│   └── yespower_vectors.json
├── SOURCE_LOCK.json
└── README.md
```

## Monetary rounding

Crakbit keeps Bitcoin-style integer right-shift halvings. Starting from 500,000,000 satoshis per block, the final non-zero subsidy era pays 1 satoshi per block and subsidy becomes zero at height 60,900,000. Because every halving truncates integer satoshis, the exact subsidy sum is 2,099,999,972,700,000 satoshis (20,999,999.72700000 CRAK), slightly below the nominal 21 million geometric limit.

The custom testnet and regtest genesis blocks have a **zero CRAK reward**, so they create no premine.

## Safety rule

No mainnet genesis block will be finalized until wallet tests, independent public testnet operation, sustained multi-node mining/reorg testing, reproducible release builds, and security review have passed in addition to the consensus/network gates already covered by CI.

## License

Crakbit project files are MIT licensed. Upstream Bitcoin Core remains under its own MIT notices. yespower source must retain its upstream BSD-style notices when vendored or distributed. CRAK-007 ASERT is adapted from the MIT-licensed Bitcoin Cash/Bitcoin ABC ASERT reference design with Crakbit-specific wide-intermediate handling for its easy CPU-test target.
