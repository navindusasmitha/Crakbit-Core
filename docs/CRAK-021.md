# CRAK-021 repository and release integrity gate

CRAK-021 makes the default-branch engineering path explicit and machine-checkable.
It is a repository/release-safety milestone, not a consensus or custody feature.

## Goals

- Keep every new milestone based on the latest `main` lineage.
- Keep one official payout execution architecture on `main`.
- Detect missing payout tests, docs, workflows or package wiring before merge.
- Prevent the old signed/broadcast executor path from silently coexisting with the current external-signing design.
- Prevent migration-era WAM branding from returning to maintained source and documentation.
- Keep expensive payout E2E CI pull-request driven and push-triggered only on `main`.
- Record the current engineering boundary in one maintained project-state document.

## Added

- `scripts/verify-repo-integrity.py`
- `.github/workflows/verify-repo-integrity.yml`
- `docs/PROJECT_STATE.md`
- `docs/CRAK-021.md`

## Packaging fix

CRAK-020 added an end-to-end payout reliability document, but the Linux package documentation list had
not yet been extended to include it. CRAK-021 updates the package documentation wiring so the current
payout/repository state travels with engineering packages instead of stopping at CRAK-019.

The package also includes this CRAK-021 document and `PROJECT_STATE.md`.

## Integrity checks

The verifier fails closed when any of these conditions is detected:

- a required official payout script, unit test, E2E test, workflow or milestone document is missing;
- `scripts/crakpool-pay.py` appears on the maintained tree, creating a second competing payout executor;
- Linux package/install scripts stop exposing one of the official payout tools;
- CRAK-018 through CRAK-021 project-state documentation is no longer packaged;
- payout E2E or repo-integrity CI loses the `main`-only push / pull-request trigger split;
- migration-era WAM branding is found in maintained source, tests, scripts, docs or workflows.

## Safety boundary

This milestone does not delete Git history, old branches or experimental draft work. It does not change
consensus, sign transactions, broadcast funds or enable mainnet.

A future custody, consensus or mainnet milestone must deliberately update the integrity policy rather than
bypassing it.

## Local verification

Run:

```bash
python3 -m py_compile scripts/verify-repo-integrity.py
python3 scripts/verify-repo-integrity.py
```

Expected success output starts with:

```text
CRAK-021 repository integrity: OK
```
