# Crakbit Core security policy

Crakbit Core is currently a v0.1 engineering/testnet project. It is not a mainnet-ready custody product.

## Reporting a vulnerability

Do not open a public issue containing an unpatched exploitable vulnerability, private key, wallet seed, worker credential, authentication secret, or private infrastructure detail.

Report security issues through a private maintainer communication channel. If GitHub private vulnerability reporting or a private Security Advisory is available for this repository, prefer that path. Include only the minimum reproduction material necessary and redact secrets from logs, screenshots and traces.

A useful report should include:

- affected component and commit/version;
- impact and realistic attack prerequisites;
- deterministic reproduction steps or a minimal proof of concept;
- whether consensus, wallet/custody, payout, pool edge, release integrity or availability is affected;
- suggested remediation when known.

## Security boundaries

The maintained project boundaries are documented in `docs/PROJECT_STATE.md`. In particular:

- node RPC is not a public mining API;
- the CRAK-028 public mining topology is `miner -> TLS crakpool-edge -> loopback crakpool -> loopback node RPC`;
- normal payout operations do not automatically sign or broadcast transactions;
- real release private keys must never be committed or stored in CI;
- passing repository CI is not equivalent to an independent external security review.

## CRAK-030 review and remediation gate

`security/SECURITY_REVIEW_POLICY.json` defines the independent-review scope and severity policy.
`security/SECURITY_REVIEW_STATUS.json` records review provenance without embedding a confidential report.
`security/SECURITY_FINDINGS.json` is the structured finding/remediation registry.

Run:

```bash
python3 scripts/security-review-gate.py validate
python3 scripts/security-review-gate.py status --json
```

A launch/release candidate must pass:

```bash
python3 scripts/security-review-gate.py launch --source-commit <40_HEX_COMMIT>
```

The gate fails closed until an independent external review is complete, all required scopes are covered, a report SHA-256 is recorded, and every material finding is independently re-tested as remediated. Critical and high findings cannot be risk accepted.

## Disclosure after remediation

Coordinate public disclosure with maintainers after a fix is available and affected operators have had a reasonable opportunity to update. The project may publish a sanitized advisory and remediation commit without publishing secrets, private infrastructure data, or unnecessary exploit detail.
