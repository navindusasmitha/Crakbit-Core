# CRAK-030 — External security review and remediation gate

CRAK-030 adds the control plane that must sit between Crakbit's current engineering/testnet state and any later mainnet activation decision.

This milestone does **not** claim that an independent external security review has already happened. The checked-in review status starts fail-closed as `not_performed`. A real reviewer must provide independent review provenance and report evidence before the launch gate can authorize a candidate.

## Threat-review scope

The mandatory review scope is defined in `security/SECURITY_REVIEW_POLICY.json` and covers:

1. consensus and yespower PoW integration;
2. P2P/network boundaries and public-node assumptions;
3. RPC, wallet and key handling;
4. payout custody and payout state transitions;
5. Stratum, accounting pool and CRAK-028 public TLS edge;
6. release supply chain, provenance and offline signing;
7. build/CI/dependency trust;
8. secrets, logging and operator data;
9. DoS/resource exhaustion/abuse paths;
10. upgrade, reorg, recovery and rollback behavior.

A review marked `complete` is invalid if any required scope is missing.

## Severity and remediation policy

CRAK-030 uses five severities: `critical`, `high`, `medium`, `low`, and `informational`.

- `critical` and `high` findings are always material and cannot be risk accepted.
- any finding explicitly marked `material=true` must reach `verified_remediated` before launch;
- `verified_remediated` requires a remediation commit plus independent re-test evidence and an evidence SHA-256;
- non-material medium/low/informational findings may be risk accepted only with an approver, reason and expiry;
- expired risk acceptance blocks launch.

The finding registry is `security/SECURITY_FINDINGS.json`. Finding IDs use `CRAK-SEC-YYYY-NNN`.

## Review evidence

`security/SECURITY_REVIEW_STATUS.json` records review metadata. A completed review requires:

- `independent_external_review_complete=true`;
- `independence_attested=true`;
- at least one independent reviewer record;
- a 40-hex reviewed commit;
- an ISO-8601 completion time;
- a SHA-256 of the external review report;
- a report reference, which may point to an operator-held confidential report;
- full required scope coverage.

The report itself does not need to be committed. Recording its digest lets operators prove which review artifact was used without publishing sensitive exploit detail.

## Post-review code drift

A release source commit must descend from the reviewed commit. After the reviewer signs off, CRAK-030 forbids code drift before launch. Only the following evidence/governance paths may change without forcing another code review:

- `security/SECURITY_REVIEW_STATUS.json`
- `security/SECURITY_FINDINGS.json`
- `docs/CRAK-030.md`

Any other changed path between the reviewed commit and the release source commit makes `security-review-gate.py launch` fail.

If remediation changes code, the final candidate should be externally re-tested/re-reviewed and the reviewed commit advanced to the post-remediation candidate before launch authorization.

## Commands

Validate the registry and state machine:

```bash
python3 scripts/security-review-gate.py validate
```

Display the current state without changing the exit code because launch is blocked:

```bash
python3 scripts/security-review-gate.py status --json
```

Fail closed for a release candidate:

```bash
python3 scripts/security-review-gate.py launch --source-commit <40_HEX_COMMIT>
```

The dedicated `Verify Crakbit Security Review` workflow validates JSON schemas/contracts, runs severity/remediation regression tests and keeps the CRAK-025 release-trust tests aligned.

## Mainnet release integration

CRAK-030 extends `release/RELEASE_POLICY.json` so the `mainnet` channel requires the CRAK-030 security-review gate. `scripts/release-trust.py manifest --channel mainnet` invokes the gate for the requested source commit and refuses to create a trusted mainnet release manifest while CRAK-030 is blocked.

Engineering/testnet artifact generation remains available for continued testing; this milestone must not be used to pretend that public-testnet deployment evidence or an external review already exists.

## Current repository state

The initial CRAK-030 status is intentionally:

```text
review_state = not_performed
independent_external_review_complete = false
launch_authorized = false
```

That is the correct state until a real independent reviewer has completed the review. CI passing only proves the gate itself behaves correctly.

## What remains after this milestone

Before mainnet activation, Crakbit still needs real deployment evidence from CRAK-026/027/028/029, a completed independent external review recorded through CRAK-030, closure/re-test of material findings, offline trusted mainnet release-key provisioning/public-key distribution, and a separate explicit mainnet activation/genesis/recovery milestone.
