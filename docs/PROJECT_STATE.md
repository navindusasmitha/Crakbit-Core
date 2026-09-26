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
- a conflicting `scripts/crakpool-pay.py` executor is absent from the official path;
- migration-era WAM branding is not reintroduced into maintained source/docs/workflows.

Git history, external upstream source and experimental branches are not rewritten or deleted by this gate.
It validates the maintained tree that is proposed for `main`.

## Experimental work

Draft/native or alternate architecture branches can remain for research. They must not be interpreted as
current release state merely because they exist in the repository. Promotion to the official path requires a
fresh PR against current `main`, current CI, and an explicit milestone that reconciles any architecture or
consensus differences.
