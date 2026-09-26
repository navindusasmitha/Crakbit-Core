# CRAK-025 — Release trust, provenance and offline signing boundary

CRAK-025 extends the reproducible release work from CRAK-022/024 with a cryptographic trust layer for distributed release artifacts.

It has two separate trust paths:

1. **GitHub keyless build provenance** for official testnet release artifacts built from `main`.
2. **Offline Ed25519 operator signing** for releases that require an explicit human release signature, including any future mainnet release.

The private release key is deliberately outside the repository and outside normal CI.

## Release manifest

`scripts/release-trust.py manifest` opens the final `.tar.gz` package and verifies:

- the external `.sha256` sidecar;
- the embedded `BUILD-MANIFEST.json`;
- the embedded package `SHA256SUMS` against every listed package file;
- the exact Crakbit source commit;
- the selected release channel policy.

It then writes a deterministic external `RELEASE-MANIFEST.json` containing the final archive hash/size, sidecar hash, package build-manifest hash, package checksum-file hash, source commit and release-policy requirements.

Example:

```bash
python3 scripts/release-trust.py manifest \
  --archive dist/crakbit-core-0.1.0-testnet-linux-x86_64.tar.gz \
  --policy release/RELEASE_POLICY.json \
  --source-commit <40-hex-main-commit> \
  --channel testnet \
  --output dist/RELEASE-MANIFEST.json
```

Re-verify downloaded bytes:

```bash
python3 scripts/release-trust.py verify \
  --manifest dist/RELEASE-MANIFEST.json \
  --bundle dist
```

## GitHub keyless provenance

On a push to `main`, `.github/workflows/verify-release-trust.yml` builds the deterministic Linux x86_64 testnet package, creates and re-verifies `RELEASE-MANIFEST.json`, and submits the archive, SHA256 sidecar and release manifest to GitHub artifact attestation using `actions/attest@v4`.

That action uses GitHub OIDC plus a short-lived Sigstore signing certificate; no long-lived signing secret is stored in the workflow.

A downloaded artifact can be checked against repository identity with GitHub CLI:

```bash
gh attestation verify \
  crakbit-core-0.1.0-testnet-linux-x86_64.tar.gz \
  --repo navindusasmitha/Crakbit-Core
```

The release manifest and `.sha256` file still need to be checked as part of the normal release bundle. Attestation does not replace CRAK-022/024 reproducibility; it binds the generated artifact to an authenticated build identity.

## Offline operator signature

CRAK-025 supports detached Ed25519 signatures for `RELEASE-MANIFEST.json`.

The repository does **not** generate or commit the real operator private key.

The operator should generate the production key on a trusted offline machine. Example OpenSSL commands are shown here only as an operational recipe:

```bash
openssl genpkey -algorithm ED25519 -out crakbit-release-ed25519-private.pem
openssl pkey \
  -in crakbit-release-ed25519-private.pem \
  -pubout \
  -out crakbit-release-ed25519-public.pem
```

The private key must stay offline/encrypted or be moved to appropriate hardware-backed custody. Do not commit it, upload it to GitHub Actions, paste it into an issue/chat, or copy it onto public release servers.

Sign a fully verified manifest on the offline signing machine:

```bash
python3 scripts/release-trust.py sign \
  --manifest RELEASE-MANIFEST.json \
  --private-key /secure/offline/crakbit-release-ed25519-private.pem \
  --signature RELEASE-MANIFEST.json.sig
```

Verify with the public key:

```bash
python3 scripts/release-trust.py verify-signature \
  --manifest RELEASE-MANIFEST.json \
  --public-key crakbit-release-ed25519-public.pem \
  --signature RELEASE-MANIFEST.json.sig
```

The public key may be distributed publicly. The private key must never enter this repository.

## Channel policy

`release/RELEASE_POLICY.json` currently defines:

- `engineering`: hashes/manifests only;
- `testnet`: GitHub provenance required, offline operator signature optional;
- `mainnet`: GitHub provenance **and** offline operator signature required.

The mainnet channel entry is only a trust-policy definition. It does not activate mainnet and does not override `SOURCE_LOCK.json` or the separate mainnet-readiness milestone.

Before an actual mainnet release, the trusted operator public key still has to be generated offline, reviewed, pinned through a dedicated repository change and distributed through an independent channel. That operational key-provisioning step is intentionally not automated here.

## Regression tests

`tests/release_trust_unit.py` verifies:

- valid release-manifest creation and verification;
- sidecar tamper rejection;
- archive tamper rejection;
- ephemeral CI-only Ed25519 signing/verification;
- signature failure after manifest mutation;
- rejection of a private key passed to the public-key verification path.

The temporary test private key exists only inside the test process temporary directory and is not a trusted project release key.

## Scope boundary

CRAK-025 provides release artifact integrity, authenticated keyless build provenance, and the offline signature protocol/custody boundary.

It does **not** by itself complete public-testnet node operations, sustained network soak testing, internet-facing pool security, miner interoperability, third-party security review, trusted offline mainnet key provisioning or mainnet activation.
