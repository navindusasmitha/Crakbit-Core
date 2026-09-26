# CRAK-024 — Independent cross-builder reproducibility

CRAK-024 extends the CRAK-022 deterministic archive contract from one build environment to two independent clean builder lanes.

The goal is not merely to create the same archive twice from one already-built binary set. The goal is to rebuild the release binaries independently, package each build independently, and fail CI unless the resulting release bytes agree.

## Builder model

The CI gate uses two different GitHub-hosted x86_64 host generations:

- builder-a: `ubuntu-22.04` host
- builder-b: `ubuntu-24.04` host

Both jobs build inside an Ubuntu 24.04 container. This keeps the userland compiler/library toolchain controlled while still using independent hosted machines and different host-image generations.

The two jobs do not share a build directory, compiler cache, materialized source tree, release archive or package output. Their only common inputs are the checked-out Crakbit commit, pinned upstream definitions and the controlled container/toolchain declaration in the workflow.

## Deterministic build inputs

`scripts/build-independent-repro.sh`:

1. requires Linux x86_64;
2. derives the exact Crakbit source commit from the checked-out Git commit unless explicitly overridden;
3. derives `SOURCE_DATE_EPOCH` from that commit;
4. sets `LC_ALL=C`, `LANG=C` and `TZ=UTC`;
5. normalizes checkout-root references with GCC `-ffile-prefix-map`, `-fdebug-prefix-map` and `-fmacro-prefix-map`;
6. configures the same wallet-enabled daemon/CLI build in each clean builder;
7. builds `crakbitd`, `crakbit-cli` and the native yespower scanner;
8. independently runs the normal CRAK-022 Linux packager.

The normal release package remains the object under comparison. CRAK-024 does not introduce a second packaging format.

## Reproducibility manifest

Each builder emits:

- the independently produced `crakbit-core-*-linux-x86_64.tar.gz`;
- its `.sha256` sidecar;
- `REPRODUCIBILITY-MANIFEST.json`;
- `BUILDER-INFO.json`.

`REPRODUCIBILITY-MANIFEST.json` is deterministic and includes:

- Crakbit source commit;
- source-date epoch;
- final archive SHA256 and size;
- sidecar SHA256 and size;
- the package's CRAK-022 `BUILD-MANIFEST.json`;
- SHA256 and size for packaged `crakbitd`;
- SHA256 and size for packaged `crakbit-cli`;
- SHA256 and size for packaged `crakminer-scan`;
- SHA256 and size for package `SHA256SUMS` and `BUILD-MANIFEST.json`.

Builder-specific information is deliberately kept out of that deterministic file. `BUILDER-INFO.json` records the builder ID, runner label, runner metadata and compiler/CMake/Python versions for audit context.

## Comparison gate

`scripts/repro-manifest.py compare` is fail-closed. It requires:

- two different non-empty builder IDs;
- every uploaded artifact to still match its recorded SHA256 and size;
- each archive sidecar to match the archive bytes;
- each package to still contain the required release binaries and manifest/checksum files;
- each package's internal member hashes to match its reproducibility manifest;
- both deterministic manifests to be exactly equal;
- the final archive and sidecar bytes to be exactly equal.

A matching archive therefore implies matching package contents, while the explicit member checks make failures easier to localize and prevent a stale/tampered JSON manifest from being accepted.

## CI workflow

`.github/workflows/verify-independent-repro.yml` has three stages:

1. fast manifest/parser regression tests;
2. two independent clean builder jobs;
3. a separate comparison job that downloads both artifacts and proves equality.

The workflow uploads a short `crakbit-repro-proof` result after a successful comparison. Builder artifacts are intentionally short-lived CI evidence rather than published releases.

## Local use

Prepare the pinned source tree first:

```bash
bash scripts/bootstrap.sh
bash scripts/materialize-locked.sh
```

Run one controlled local builder lane:

```bash
bash scripts/build-independent-repro.sh local-a
```

A real CRAK-024 proof requires a second independent build. Given two bundles:

```bash
python3 scripts/repro-manifest.py compare \
  --left /path/to/builder-a \
  --right /path/to/builder-b
```

Fast comparator regression test:

```bash
python3 tests/repro_manifest_unit.py
```

## Scope boundary

Passing CRAK-024 proves reproducibility for the current Linux x86_64 controlled-toolchain path used by the two independent CI builders.

It does **not** claim:

- reproducibility across arbitrary compilers or Linux distributions;
- x86_64/ARM64 cross-architecture byte identity;
- cryptographic release signing or key custody;
- public-testnet operational readiness;
- internet-facing pool security;
- mainnet readiness.

Those remain separate engineering/security milestones.