# Crakbit Core project state

This document defines the maintained engineering path for the default `main` branch.
It is intentionally narrower than the complete Git history: experimental branches and
old milestone approaches may exist, but they are not release authority unless merged
into `main` through the current CI gate.

## Integration policy

The default integration path is:

1. Start every new milestone from the latest `main` commit.
2. Put code, tests, documentation, packaging changes and CI for that milestone on one branch.
3. Open a pull request back to `main`.
4. Require the current milestone-specific checks plus the existing core checks to complete successfully.
5. Merge only after the branch is not behind `main` and the PR is mergeable.
6. Start the next milestone from the new `main` merge commit.

Do not force-reset `main` or use old milestone branches as a new base unless a dedicated
recovery decision explicitly requires it.

## Current payout engineering path

The maintained payout stack on `main` is deliberately split by responsibility:

- `scripts/crakpool-accounting.py` — persistent share/block/credit accounting.
- `scripts/crakpool-payout.py` — canonical-chain reconciliation and mature non-broadcast payout planning.
- `scripts/crakpool-paytx.py` — funded unsigned PSBT creation, txid attachment, confirmation verification and settlement.
- `scripts/crakpool-payguard.py` — immediate preflight checks plus guarded attach/cancel recovery.
- `scripts/crakpool-payops.py` — read/monitor-first operator state and explicit confirmation refresh.
- `tests/payout_e2e_smoke.sh` — isolated regtest proof of the complete plan-to-paid lifecycle.

The normal operator flow remains:

`plan -> build PSBT -> preflight -> external sign/broadcast -> guarded attach -> confirmations -> settle`

The maintained default branch does not include a second automatic signed-transaction payout executor.
A file named `scripts/crakpool-pay.py` is therefore treated as a conflicting legacy path by CRAK-021.
Any future change to custody/signing policy must be a new, explicitly reviewed milestone rather than a
silent reintroduction of an older branch design.

## Network and custody boundary

Current payout tooling is engineering infrastructure for `regtest` and `testnet4` workflows.
CRAK-020 uses automatic signing/broadcast only inside an isolated regtest CI test so the end-to-end
state machine can be verified. That CI behavior does not make the normal operator path automatic.

No mainnet readiness claim is made by this document. Mainnet activation requires a separate explicit
milestone with its own security, operations, release and network-readiness gates.

## Repository integrity policy

CRAK-021 adds `scripts/verify-repo-integrity.py` and a dedicated CI workflow. The gate verifies that:

- the official payout scripts and their unit/E2E tests are present;
- required milestone workflows and documentation are present;
- Linux package and install scripts still expose the official payout toolchain;
- current milestone documentation is included in the Linux package;
- the full payout E2E workflow is pull-request driven and only push-triggered on `main`;
- deterministic-release, ARM64-runtime, independent-builder and release-trust gates cannot silently disappear;
- a conflicting `scripts/crakpool-pay.py` executor is absent from the official path;
- private release-key material is not committed under the release trust surface;
- migration-era WAM branding is not reintroduced into maintained source/docs/workflows.

Git history, external upstream source and experimental branches are not rewritten or deleted by this gate.
It validates the maintained tree that is proposed for `main`.

## Release reproducibility policy

CRAK-022 defines the deterministic release-packaging contract for the Linux engineering package.
For identical input binaries, source commit, version and `SOURCE_DATE_EPOCH`, `scripts/package-linux.sh`
must produce byte-for-byte identical `.tar.gz` archives and matching SHA256 sidecars.

Every package must contain `share/doc/crakbit-core/BUILD-MANIFEST.json` with the exact Crakbit source
commit, normalized release epoch, target Linux architecture, mainnet-enabled state, pinned Bitcoin Core
commit, pinned yespower commit and locked yespower profile.

The archive layer normalizes tar ordering, mtimes, uid/gid and gzip timestamp metadata. The dedicated
`Verify Crakbit Reproducible Release` workflow builds the release inputs and runs
`tests/package_reproducibility_smoke.sh` to prove the archive contract on Linux CI.

CRAK-024 extends that contract to independent compiler/build jobs for the controlled Linux x86_64 path.
It does not replace CRAK-022; CRAK-022 proves packaging determinism for one input set, while CRAK-024
proves two clean builders independently regenerate the same release inputs and final archive.

Cross-distribution/compiler-family reproducibility, public testnet operations and mainnet activation remain
separate gates. Release artifact trust is governed separately by CRAK-025 below.

## Native ARM64 runtime policy

CRAK-023 adds a native ARM64 build/package/runtime gate. The dedicated
`Verify Crakbit ARM64 Runtime` workflow must run on the GitHub-hosted `ubuntu-24.04-arm` runner and
must fail if the host architecture is not `aarch64`.

The ARM64 gate builds the wallet-enabled node, CLI and native yespower scanner on ARM64 hardware,
requires ARM64 ELF binaries, creates the normal `linux-arm64` package, verifies its CRAK-022 build
manifest and checksums, installs it, and executes the node, wallet, RPC miner, native miner, persistent
pool, Stratum worker and payout/operations entry points on isolated regtest.

A cross-compile-only or qemu-only result does not satisfy CRAK-023. Passing this gate proves the current
Ubuntu 24.04 ARM64 package path on native hosted hardware; it does not prove every Linux distribution or
ARM board, public-testnet readiness, internet-facing pool security or mainnet readiness.

## Independent cross-builder policy

CRAK-024 adds a dedicated `Verify Crakbit Independent Reproducibility` workflow for Linux x86_64.
Two clean builder jobs run on different GitHub-hosted Ubuntu host generations (`ubuntu-22.04` and
`ubuntu-24.04`) while using the same controlled Ubuntu 24.04 container userland/toolchain.

Each builder independently:

- fetches the pinned upstreams;
- materializes the locked Crakbit source tree;
- normalizes source/debug/macro paths relative to the checkout;
- derives one `SOURCE_DATE_EPOCH` from the checked-out Crakbit commit;
- compiles `crakbitd`, `crakbit-cli` and the native yespower scanner;
- creates the normal deterministic Linux package;
- records a deterministic reproducibility manifest plus separate builder provenance.

A third job downloads both builder results and fails unless the final archive, SHA sidecar, packaged
binaries, internal package checksum file and CRAK-022 build manifest all agree. It also re-hashes each
uploaded artifact against its own manifest so stale or modified proof files cannot pass by JSON equality
alone.

Passing CRAK-024 proves controlled-toolchain independent-builder reproducibility for the current Linux
x86_64 path. It does not claim arbitrary compiler/distribution reproducibility and does not imply public-
testnet operational readiness, pool perimeter security or mainnet readiness.

## Release trust and signing policy

CRAK-025 adds `release/RELEASE_POLICY.json`, `scripts/release-trust.py`, regression tests and the dedicated
`Verify Crakbit Release Trust` workflow.

The release-trust chain is:

`deterministic package -> SHA256 sidecar -> embedded BUILD-MANIFEST + SHA256SUMS -> RELEASE-MANIFEST.json -> authenticated provenance -> optional/required offline operator signature`

For official testnet release artifacts produced from `main`, GitHub keyless artifact attestation is required.
The workflow uses GitHub OIDC and short-lived Sigstore signing material rather than a long-lived project
secret. The archive, SHA sidecar and external release manifest are all attested as release subjects.

CRAK-025 also defines a detached Ed25519 signature protocol for the external `RELEASE-MANIFEST.json`.
A real operator private release key is intentionally not created or stored by the repository or CI. Any
future mainnet release requires offline operator signing in addition to authenticated build provenance.
The trusted operator public key must be generated, reviewed and pinned through a separate repository
change before a mainnet release; private-key material must never be committed.

The `mainnet` entry in `release/RELEASE_POLICY.json` is a trust-policy rule only. It does not enable mainnet,
change consensus parameters or bypass the explicit mainnet activation milestone.

## Launch gates after CRAK-025

The engineering chain can be used on regtest/testnet4 today, but a public network launch is treated as an
operations/security event rather than only a build milestone.

Major remaining launch gates are:

1. public testnet bootstrap infrastructure: independently hosted seed/boot nodes, documented peer/bootstrap configuration and recovery procedures;
2. sustained public testnet soak: multi-node uptime, continuous mining, natural/forced reorg observation, restart/recovery and monitoring evidence;
3. internet-facing pool perimeter hardening: TLS or protected transport where appropriate, authentication/abuse controls, rate limiting, RPC isolation and operational logging;
4. broader miner/node interoperability and upgrade/release rehearsal across supported x86_64/ARM64 environments;
5. external security/code review and remediation of material findings;
6. offline trusted release-key provisioning/public-key distribution for mainnet releases;
7. a separate explicit mainnet activation milestone covering final network parameters/genesis, seeds/checkpoints policy, release procedure and rollback/emergency operations.

Public testnet can be launched before the mainnet-only gates, once its bootstrap, monitoring and security
requirements are satisfied. Mainnet must not be activated merely because CI and testnet pass.

## Experimental work

Draft/native or alternate architecture branches can remain for research. They must not be interpreted as
current release state merely because they exist in the repository. Promotion to the official path requires a
fresh PR against current `main`, current CI, and an explicit milestone that reconciles any architecture or
consensus differences.
