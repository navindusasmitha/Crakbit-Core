# Crakbit Core project state

This document defines the maintained engineering path for the default `main` branch.
Experimental branches and old milestone approaches may exist, but they are not release
authority unless merged into `main` through the current CI gate.

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
A file named `scripts/crakpool-pay.py` is treated as a conflicting legacy path by CRAK-021. Any future
change to custody/signing policy must be a new, explicitly reviewed milestone.

## Network and custody boundary

Current payout tooling is engineering infrastructure for `regtest` and `testnet4` workflows.
CRAK-020 uses automatic signing/broadcast only inside an isolated regtest CI test so the end-to-end
state machine can be verified. That CI behavior does not make the normal operator path automatic.

No mainnet readiness claim is made by this document. Mainnet activation requires a separate explicit
milestone with its own security, operations, release and network-readiness gates.

## Repository integrity policy

CRAK-021 adds `scripts/verify-repo-integrity.py` and a dedicated CI workflow. The gate verifies the
maintained payout path, package/install wiring, release-reproducibility gates, ARM64 runtime gate,
independent-builder gate, release-trust gate, absence of the competing signed payout executor, absence
of committed private release keys and absence of migration-era branding from maintained product files.

CRAK-027 and CRAK-028 add separate fail-closed operations/security integrity gates for public-testnet
soak requirements and the internet-facing pool perimeter. They supplement rather than replace CRAK-021.

## Release reproducibility policy

CRAK-022 defines the deterministic Linux release-packaging contract. For identical input binaries,
source commit, version and `SOURCE_DATE_EPOCH`, `scripts/package-linux.sh` must produce byte-for-byte
identical archives and SHA256 sidecars. Every package contains `BUILD-MANIFEST.json` with source,
architecture and pinned-upstream provenance.

CRAK-024 extends that contract to independent x86_64 builder lanes. Two clean builders use different
host generations with the same controlled build userland, normalize source/debug paths and compare the
final archive plus packaged `crakbitd`, `crakbit-cli`, `crakminer-scan`, checksums and build manifest.

Passing these gates proves the controlled release path; it does not claim arbitrary compiler/distribution
reproducibility or public-network operational readiness.

## Native ARM64 runtime policy

CRAK-023 uses a native GitHub-hosted `ubuntu-24.04-arm` runner and fails if the host architecture is not
`aarch64`. It builds and installs the normal ARM64 package and exercises the node, wallet, RPC/native
mining, Stratum pool/worker and payout/operations entry points on isolated regtest. Cross-compile-only or
emulated results do not satisfy this gate.

## Release trust and signing policy

CRAK-025 adds `release/RELEASE_POLICY.json`, `scripts/release-trust.py`, regression tests and the dedicated
`Verify Crakbit Release Trust` workflow.

The release-trust chain is:

`deterministic package -> SHA256 sidecar -> embedded BUILD-MANIFEST + SHA256SUMS -> RELEASE-MANIFEST.json -> authenticated provenance -> optional/required offline operator signature`

Official testnet artifacts produced from `main` require GitHub keyless artifact attestation. The workflow
uses GitHub OIDC and short-lived Sigstore signing material rather than a long-lived project secret.

Future mainnet releases additionally require an offline Ed25519 operator signature. A real operator
private release key is intentionally not generated or stored by repository CI. The trusted operator public
key must be generated, reviewed and pinned through a separate repository change before mainnet release.

## Public testnet bootstrap policy — CRAK-026

CRAK-026 adds `network/TESTNET_BOOTSTRAP.json`, strict public-ready validation, deterministic `addnode=`
rendering, P2P-only health probing, RPC-isolation checks and deployment/recovery documentation.

The checked-in inventory intentionally contains disabled `.invalid` placeholders. Repository CI must not
pretend that placeholder hosts are public infrastructure. Public-ready qualification requires at least two
enabled public endpoints in at least two independent provider/region failure domains with node RPC kept
private.

Passing CRAK-026 proves the bootstrap control plane. It does not prove that real public seed nodes have
already been provisioned.

## Public testnet soak policy — CRAK-027

CRAK-027 adds `network/SOAK_POLICY.json`, local-RPC observation collection, multi-node availability/tip
convergence/mining-progress evaluation, explicit restart/recovery evidence, explicit reorg/recovery
evidence and a fail-closed operations integrity gate.

The candidate gate requires at least 24 hours of real observations and restart recovery on every enabled
node. The launch gate requires at least 72 hours plus the required recovered reorg evidence. RPC failures
are recorded as unhealthy samples rather than being silently dropped.

Passing CRAK-027 CI proves the collector/evaluator contract only. The repository does not fabricate
24-hour or 72-hour evidence. Real CRAK-026 public nodes must be provisioned and observed before a public
testnet can be described as having passed the soak gate.

## Internet-facing pool security policy — CRAK-028

The maintained CRAK-028 public pool topology is:

`miner -> TLS crakpool-edge -> loopback crakpool -> loopback crakbit RPC`

The internal accounting pool is a trusted loopback service. Direct public binding of that internal service
is outside the supported CRAK-028 deployment. `crakpool-edge` is the public boundary and enforces the
reviewed `network/POOL_SECURITY.json` policy.

For a non-loopback edge bind, CRAK-028 requires TLS 1.2 or newer, a private worker credential store and a
loopback-only upstream. Worker credentials use PBKDF2-HMAC-SHA256 with random salts and constant-time
verification. The edge also enforces worker/session identity binding, a small Stratum method allowlist,
line limits, authentication/idle timeouts, global/per-IP connection limits, message/share-submit rate
limits, a global submit-pressure limit, temporary bans after repeated auth failures and structured
security events that do not contain worker secrets.

The official `crakminer-stratum` client supports verified TLS and non-argv secret input through
`--password-file` or `--password-stdin`. Certificate verification and hostname checking stay enabled by
default; the maintained path does not provide an insecure public-TLS bypass.

Passing CRAK-028 CI proves the repository/runtime perimeter controls. It does not claim that a production
public pool has already been deployed, firewall-reviewed, DDoS-tested or externally penetration-tested.

## Launch gates after CRAK-028

The build/release/control-plane chain can be used on regtest/testnet4 today, but public launch remains an
operations/security event. Major outstanding gates are:

1. provision real CRAK-026 bootstrap nodes in independent failure domains and replace the disabled placeholders;
2. execute and retain real CRAK-027 24-hour candidate and 72-hour launch soak evidence, including restart and reorg recovery;
3. deploy CRAK-028 on the real public pool host with firewall/RPC isolation, certificate lifecycle, log retention and abuse/DDoS observations;
4. broader miner/node interoperability and upgrade/release rehearsal across supported x86_64/ARM64 environments;
5. external security/code review and remediation of material findings;
6. offline trusted mainnet release-key provisioning and public-key distribution;
7. a separate explicit mainnet activation milestone covering final network parameters/genesis, seeds/checkpoints policy, release procedure and rollback/emergency operations.

Public testnet may launch only after its real bootstrap, soak and perimeter deployment evidence is
satisfactory. Mainnet must not be activated merely because CI and testnet gates pass.

## Experimental work

Alternate architecture branches may remain for research. They are not current release state merely
because they exist. Promotion to the official path requires a fresh PR against current `main`, current CI
and an explicit milestone that reconciles architecture/consensus differences.
