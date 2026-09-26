# Crakbit Core

Crakbit Core is a Bitcoin-style UTXO Proof-of-Work blockchain project focused on CPU mining.

> **Engineering status:** this repository is still a v0.1 testnet/regtest project. It is not mainnet-ready and does not claim production custody or network safety. See `docs/PROJECT_STATE.md` for the maintained default-branch path and release policy.

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

## Implemented milestones

- CRAK-004: pinned yespower build integration
- CRAK-005: yespower block-header identity hash + deterministic vector
- CRAK-006: isolated Crakbit testnet/regtest identity + zero-reward custom genesis blocks
- CRAK-007: integer-only ASERT testnet difficulty + frozen Python/C++ vectors
- CRAK-008: 5 CRAK subsidy, 2,100,000-block halving, 100-block maturity, zero premine + compiled boundary vectors
- CRAK-009: full `crakbitd` / `crakbit-cli` build, CPU mining RPC, three-node sync, reorg and invalid-block smoke
- CRAK-010: wallet send/receive/restart persistence smoke
- CRAK-011: Linux package builder, installer, safe node launcher, checksums and package smoke
- CRAK-012: packaged RPC mining controller with worker and CPU-duty-cycle controls
- CRAK-013: native external yespower miner using `getblocktemplate` -> native nonce scanning -> `submitblock`
- CRAK-014: Stratum V1 subset pool + external CPU workers, unique extranonces, share verification and block submission
- CRAK-015: persistent SQLite share/block/credit accounting, proportional/PPLNS rewards, worker statistics and vardiff
- CRAK-016: canonical reward reconciliation, payout-address registration, 100-confirmation maturity, deterministic non-broadcast batches and reorg invalidation
- CRAK-017: operator-controlled funded **unsigned PSBT** lifecycle, txid attachment, confirmation verification and settlement; normal use does not sign or broadcast
- CRAK-018: immediate preflight/recovery guard for source canonicality, maturity, recipient outputs, fee caps, fresh attach and safe unbroadcast cancellation
- CRAK-019: payout operations monitor with list/show/summary, next-action classification, stale detection and explicit confirmation refresh
- CRAK-020: isolated regtest end-to-end proof from mature payout plan through PSBT, preflight, CI-only sign/broadcast, confirmations and final paid state
- CRAK-021: repository/release integrity gate, maintained project-state policy, package-doc alignment and legacy/conflicting-path protection
- CRAK-022: deterministic Linux release archive, source/build manifest and byte-identical package reproducibility smoke
- CRAK-023: native ARM64 build/package/install/runtime validation for node, wallet, mining, pool, Stratum and payout tooling
- CRAK-024: independent x86_64 clean builders, controlled toolchain/path normalization, packaged-binary hashes and byte-identical release proof
- CRAK-025: deterministic external release manifest, GitHub keyless SLSA provenance, offline Ed25519 signature protocol and private-key custody boundary

## Build a Linux testnet package

```bash
bash scripts/build-linux.sh
```

The package includes:

```text
bin/crakbitd
bin/crakbit-cli
bin/crakbit-start
bin/crakbit-mine
bin/crakminer
bin/crakminer-native
bin/crakminer-scan
bin/crakpool
bin/crakpool-stats
bin/crakpool-payout
bin/crakpool-paytx
bin/crakpool-payguard
bin/crakpool-payops
bin/crakminer-stratum
install.sh
SHA256SUMS
share/doc/crakbit-core/BUILD-MANIFEST.json
share/doc/crakbit-core/
share/licenses/
```

Install an extracted package:

```bash
bash install.sh ~/.local
```

Python 3 handles template/RPC/Stratum/accounting/reconciliation/payout orchestration. yespower hashing itself runs in the native `crakminer-scan` binary.

## Node and native CPU mining

Start regtest:

```bash
CRAKBIT_DATADIR="$HOME/.crakbit-regtest" crakbit-start regtest
crakbit-cli -regtest -datadir="$HOME/.crakbit-regtest" createwallet miner
```

Start testnet4:

```bash
crakbit-start testnet4
```

Low-end native CPU mining example:

```bash
crakminer-native \
  --network testnet4 \
  --wallet miner \
  --threads 1 \
  --cpu-limit 30
```

`--cpu-limit` is an approximate per-worker duty cycle, not a kernel-enforced quota.

## Pool mining and accounting

`crakpool` is the persistent CRAK-015 accounting/vardiff pool command. The CRAK-014 protocol engine remains packaged internally as `crakpool-base.py`.

Start a localhost PPLNS pool:

```bash
crakpool \
  --network testnet4 \
  --wallet pool \
  --listen 127.0.0.1 \
  --port 3333 \
  --share-difficulty 0.0001 \
  --payout-mode pplns \
  --pplns-shares 1000 \
  --pool-fee-bps 0
```

Connect another CPU machine:

```bash
crakminer-stratum \
  --pool POOL_IP:3333 \
  --worker pc1 \
  --threads 1 \
  --cpu-limit 30
```

For LAN/testnet deployment, expose only the Stratum port to miners and keep Crakbit node RPC private.

The default pool ledger is stored under the selected node datadir as:

```text
crakpool-testnet4.sqlite3
```

Inspect accounting state:

```bash
crakpool-stats --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" --window 600
```

Reward modes are `proportional` and `pplns`. `--pool-fee-bps` is accounting-only; `100` means 1%, and the default is `0`.

Vardiff is enabled by default and targets roughly one accepted share every 15 seconds per worker. Useful controls include:

```text
--no-vardiff
--vardiff-min <difficulty>
--vardiff-max <difficulty>
--vardiff-target-seconds 15
--vardiff-retarget-seconds 90
```

## Official payout lifecycle — CRAK-016 through CRAK-020

The maintained default-branch flow deliberately separates accounting, transaction construction, preflight and operations monitoring:

```text
plan -> build PSBT -> preflight -> external sign/broadcast -> guarded attach -> confirmations -> settle
```

### 1. Register a worker payout address

```bash
crakpool-payout \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  register \
  --network testnet4 \
  --worker pc1 \
  --address <CRAK_ADDRESS>
```

### 2. Reconcile and create a mature non-broadcast plan

```bash
crakpool-payout \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  plan \
  --network testnet4 \
  --wallet pool \
  --maturity 100 \
  --minimum-sats 100000 \
  --max-outputs 100
```

Selected credits atomically move from `pending` to `planned`. Reorg reconciliation can orphan unpaid credits and invalidate an unbroadcast plan whose source block is no longer canonical.

### 3. Build an unsigned funded PSBT

```bash
crakpool-paytx \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  build-psbt \
  --network testnet4 \
  --wallet pool \
  --batch <BATCH_ID> \
  --fee-rate 1.0
```

CRAK-017 does not sign or broadcast in normal operator use.

### 4. Run the CRAK-018 preflight

Run immediately before external signing/broadcast:

```bash
crakpool-payguard \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  preflight \
  --network testnet4 \
  --wallet pool \
  --batch <BATCH_ID> \
  --max-fee-sats <MAX_FEE_SATS>
```

After signing and broadcasting with separate wallet/operator tooling, attach the resulting txid through the fresh-preflight guard:

```bash
crakpool-payguard \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  guarded-attach \
  --batch <BATCH_ID> \
  --txid <TXID>
```

Cancellation is restricted to a PSBT the operator has explicitly verified was never signed or broadcast:

```bash
crakpool-payguard \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  cancel \
  --network testnet4 \
  --wallet pool \
  --batch <BATCH_ID> \
  --confirm-not-broadcast
```

### 5. Monitor and refresh confirmations

```bash
crakpool-payops --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" summary
crakpool-payops --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" list
```

Explicit refresh:

```bash
crakpool-payops \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  refresh \
  --network testnet4 \
  --wallet pool \
  --batch <BATCH_ID>
```

`crakpool-payops` never signs, broadcasts or auto-settles.

### 6. Settle after the confirmation gate

```bash
crakpool-paytx \
  --db "$HOME/.crakbit/crakpool-testnet4.sqlite3" \
  settle \
  --network testnet4 \
  --wallet pool \
  --batch <BATCH_ID> \
  --confirmations 6
```

CRAK-020 proves the complete lifecycle on isolated regtest CI, including a CI-only sign/broadcast step and exact worker-wallet receipt. That automated test does not change the normal external-signing custody boundary.

## Repository and release integrity — CRAK-021

Run the fast default-branch integrity gate locally:

```bash
python3 scripts/verify-repo-integrity.py
```

It verifies the official payout scripts/tests/workflows/docs, package/install wiring, current E2E CI trigger policy, deterministic release contracts, native ARM64 runtime gate, independent-builder reproducibility gate, CRAK-025 release-trust policy/workflow, absence of a competing legacy signed payout executor, absence of private release keys under the release surface, and absence of migration-era branding in maintained product source/docs.

## Reproducible Linux package — CRAK-022

For identical binaries, source commit, version and source-date epoch, the Linux package archive must be byte-for-byte reproducible. Every archive includes `share/doc/crakbit-core/BUILD-MANIFEST.json` with source and pinned-upstream provenance.

The dedicated `Verify Crakbit Reproducible Release` workflow runs `tests/package_reproducibility_smoke.sh` and validates deterministic tar/gzip metadata, archive SHA256 and internal package hashes.

## Native ARM64 runtime — CRAK-023

The dedicated `Verify Crakbit ARM64 Runtime` workflow uses a native `ubuntu-24.04-arm` runner. It builds ARM64 `crakbitd`, `crakbit-cli` and `crakminer-scan`, creates and installs the `linux-arm64` package, then exercises regtest node/wallet mining, native yespower mining, Stratum pool/worker accounting and the packaged payout/operations tools.

A cross-compile-only or emulated result does not satisfy this gate. See `docs/CRAK-023.md` for the exact runtime contract.

## Independent cross-builder reproducibility — CRAK-024

The dedicated `Verify Crakbit Independent Reproducibility` workflow rebuilds the Linux x86_64 release on two independent hosted builder lanes. The hosts use different GitHub Ubuntu generations while both build inside a controlled Ubuntu 24.04 userland.

CRAK-024 normalizes source/debug paths and source time, then compares the final package bytes plus packaged `crakbitd`, `crakbit-cli`, `crakminer-scan`, `BUILD-MANIFEST.json` and package checksums. Machine-specific provenance is stored separately from the deterministic equality manifest.

Fast comparator regression test:

```bash
python3 tests/repro_manifest_unit.py
```

See `docs/CRAK-024.md` for the exact builder and comparison contract.

## Trusted release provenance — CRAK-025

`release/RELEASE_POLICY.json` defines the release-channel trust requirements. `scripts/release-trust.py` validates the final archive, external SHA256 sidecar, embedded `BUILD-MANIFEST.json` and embedded package `SHA256SUMS`, then creates a deterministic external `RELEASE-MANIFEST.json`.

Fast release-trust regression test:

```bash
python3 tests/release_trust_unit.py
```

On `main`, the dedicated `Verify Crakbit Release Trust` workflow creates GitHub keyless SLSA provenance attestations for the testnet archive, SHA sidecar and release manifest. A downloaded archive can be checked against repository identity with GitHub CLI:

```bash
gh attestation verify \
  crakbit-core-0.1.0-testnet-linux-x86_64.tar.gz \
  --repo navindusasmitha/Crakbit-Core
```

Future mainnet releases additionally require a detached offline Ed25519 operator signature over `RELEASE-MANIFEST.json`. The real private release key is intentionally not generated or stored by this repository/CI and must never be committed.

See `docs/CRAK-025.md` for the release-manifest, provenance and offline-key custody contract.

See also:

- `docs/PROJECT_STATE.md` — official integration, payout, release and network boundaries
- `docs/CRAK-021.md` — integrity-gate details
- `docs/CRAK-022.md` — reproducible archive contract
- `docs/CRAK-023.md` — native ARM64 runtime contract
- `docs/CRAK-024.md` — independent cross-builder reproducibility contract
- `docs/CRAK-025.md` — release trust, provenance and offline signing boundary

## Verification

Fast checks:

```bash
python3 scripts/verify-lock.py
python3 scripts/verify-asert-vectors.py
python3 tests/stratum_protocol_unit.py
python3 tests/pool_accounting_unit.py
python3 tests/payout_planner_unit.py
python3 tests/paytx_unit.py
python3 tests/payguard_unit.py
python3 tests/payops_unit.py
python3 tests/repro_manifest_unit.py
python3 tests/release_trust_unit.py
python3 scripts/verify-repo-integrity.py
```

Dedicated CI also covers three-node/reorg behavior, wallet persistence, native mining, Stratum mining, accounting/vardiff persistence, payout maturity/reorg planning, CRAK-017/018/019 unit contracts, Linux package smoke, CRAK-020 full regtest payout E2E, CRAK-022 reproducible Linux archives, CRAK-023 native ARM64 runtime validation, CRAK-024 independent cross-builder release equality and CRAK-025 release trust/provenance.

## Network status

Bitcoin mainnet, Bitcoin testnet3 and signet remain unavailable as user-selectable Crakbit networks. The current usable development networks are Crakbit testnet4 and regtest.

Crakbit testnet currently has no inherited Bitcoin DNS seeds, minimum-chain-work, or assume-valid checkpoint.

## Monetary rounding

Crakbit keeps Bitcoin-style integer right-shift halvings. Starting from 500,000,000 satoshis per block, subsidy becomes zero at height 60,900,000. Integer truncation makes the exact subsidy sum 2,099,999,972,700,000 satoshis (20,999,999.72700000 CRAK), slightly below the nominal 21 million geometric limit.

The custom testnet and regtest genesis blocks have a **zero CRAK reward**, so they create no premine.

## Important status

This repository is still a **v0.1 engineering/testnet project**. It is **not mainnet-ready** and does not claim production safety.

Remaining major gates include independent public testnet bootstrap nodes, sustained public mining/reorg/uptime observation, internet-facing pool security controls, broader miner/node interoperability, external security/code review, offline trusted mainnet release-key provisioning/public-key distribution, and a separate explicit mainnet activation milestone.

No mainnet genesis block will be finalized until those gates pass review.

## License

Crakbit project files are MIT licensed. Upstream Bitcoin Core remains under its own MIT notices. yespower source retains its upstream BSD-style notices; binary packages carry the exact vendored yespower source/header material used by the build. CRAK-007 ASERT is adapted from the MIT-licensed Bitcoin Cash/Bitcoin ABC ASERT reference design with Crakbit-specific wide-intermediate handling for the easy CPU-test target.
