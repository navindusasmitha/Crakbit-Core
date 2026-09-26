# CRAK-022 reproducible Linux release packaging

CRAK-022 adds a deterministic release-packaging contract for the current Linux testnet/regtest engineering package.

This milestone does **not** claim that the compiler output is reproducible across operating systems, compiler versions, CPU architectures, or builders. It makes the archive layer reproducible when the input binaries, source tree and release metadata are the same, and records enough provenance inside the package to audit what was packaged.

## Deterministic archive contract

`scripts/package-linux.sh` now derives or accepts two release inputs:

- `CRAKBIT_SOURCE_COMMIT` — the exact 40-hex repository commit being packaged. If omitted, the current Git `HEAD` is used.
- `SOURCE_DATE_EPOCH` — the normalized archive timestamp. If omitted, it is derived from the selected source commit.

The generated `.tar.gz` archive uses:

- lexical tar entry ordering;
- one normalized mtime for all archive entries;
- numeric uid/gid `0` instead of builder-specific ownership;
- normalized package directory and documentation permissions;
- gzip `-n`, so the gzip header does not record the builder filename or wall-clock timestamp.

Given identical package inputs, two packaging runs are expected to produce byte-for-byte identical archives and identical SHA256 sidecars.

## Build manifest

Every package contains:

`share/doc/crakbit-core/BUILD-MANIFEST.json`

The manifest records:

- package schema and version;
- Linux architecture;
- exact Crakbit source commit;
- normalized source-date epoch;
- mainnet-enabled state from `SOURCE_LOCK.json`;
- pinned Bitcoin Core commit;
- pinned yespower commit;
- locked yespower profile;
- the archive-normalization contract.

The existing top-level `SHA256SUMS` includes the manifest, so changing provenance metadata changes the package content hash intentionally.

## CI verification

`tests/package_reproducibility_smoke.sh` packages the same already-built binaries twice with the same source commit and epoch, then verifies:

1. the two `.tar.gz` archives are byte-for-byte identical;
2. their `.sha256` sidecars are identical;
3. the internal `SHA256SUMS` file verifies;
4. tar entries are lexically ordered;
5. every tar entry has normalized uid/gid and mtime;
6. the gzip header timestamp is zero;
7. `BUILD-MANIFEST.json` matches the repository source lock and requested release inputs.

The smoke is wired into the existing full `Verify Crakbit v0.1` build so it reuses the binaries already compiled by that job rather than starting a second expensive compiler job.

## Scope boundary

CRAK-022 is one step toward the broader release-readiness work listed in the README. It does not yet prove:

- reproducible compiler output on independent machines;
- cross-distribution or cross-platform reproducibility;
- ARM64 runtime correctness;
- signed release artifacts or release-key custody;
- public testnet or mainnet readiness.

Those remain separate review gates.
