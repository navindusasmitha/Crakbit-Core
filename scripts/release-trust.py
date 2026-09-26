#!/usr/bin/env python3
"""CRAK-025 release trust manifest, verification and detached Ed25519 signing.

Private keys are never generated, stored, or discovered by this tool. Operators pass
an explicit private-key path only to the `sign` subcommand. Public verification is
performed with OpenSSL Ed25519 and the deterministic external release manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
RELEASE_MANIFEST = "RELEASE-MANIFEST.json"
BUILD_MANIFEST_REL = "share/doc/crakbit-core/BUILD-MANIFEST.json"
CHECKSUMS_REL = "SHA256SUMS"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_write(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def archive_root(tf: tarfile.TarFile) -> str:
    roots = {m.name.split("/", 1)[0] for m in tf.getmembers() if m.name and m.name != "."}
    if len(roots) != 1:
        raise RuntimeError(f"release archive must contain exactly one top-level directory, found {sorted(roots)}")
    return next(iter(roots))


def member_bytes(tf: tarfile.TarFile, name: str) -> bytes:
    try:
        member = tf.getmember(name)
    except KeyError as exc:
        raise RuntimeError(f"release archive missing required member: {name}") from exc
    if not member.isfile():
        raise RuntimeError(f"release archive member is not a regular file: {name}")
    f = tf.extractfile(member)
    if f is None:
        raise RuntimeError(f"unable to read release archive member: {name}")
    return f.read()


def verify_internal_checksums(tf: tarfile.TarFile, root: str, checksum_text: str) -> dict[str, str]:
    expected: dict[str, str] = {}
    for raw_line in checksum_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            raise RuntimeError(f"invalid package SHA256SUMS line: {raw_line!r}")
        rel = parts[1].lstrip("* ")
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise RuntimeError(f"unsafe package checksum path: {rel!r}")
        if rel in expected:
            raise RuntimeError(f"duplicate package checksum entry: {rel}")
        expected[rel] = parts[0].lower()

    if not expected:
        raise RuntimeError("package SHA256SUMS is empty")

    for rel, digest in sorted(expected.items()):
        actual = sha256_bytes(member_bytes(tf, f"{root}/{rel}"))
        if actual != digest:
            raise RuntimeError(f"package internal SHA256 mismatch: {rel}")
    return expected


def inspect_archive(archive: Path) -> dict[str, Any]:
    with tarfile.open(archive, mode="r:gz") as tf:
        root = archive_root(tf)
        build_raw = member_bytes(tf, f"{root}/{BUILD_MANIFEST_REL}")
        checksum_raw = member_bytes(tf, f"{root}/{CHECKSUMS_REL}")
        try:
            build_manifest = json.loads(build_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("package BUILD-MANIFEST.json is invalid") from exc
        try:
            checksum_text = checksum_raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("package SHA256SUMS is not UTF-8") from exc
        internal = verify_internal_checksums(tf, root, checksum_text)

    return {
        "package_root": root,
        "build_manifest": build_manifest,
        "build_manifest_sha256": sha256_bytes(build_raw),
        "sha256sums_sha256": sha256_bytes(checksum_raw),
        "verified_internal_files": len(internal),
    }


def verify_sidecar(archive: Path, sidecar: Path) -> str:
    if not sidecar.is_file():
        raise RuntimeError(f"missing release SHA256 sidecar: {sidecar}")
    parts = sidecar.read_text(encoding="utf-8").strip().split()
    if len(parts) < 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
        raise RuntimeError(f"invalid release SHA256 sidecar: {sidecar.name}")
    if Path(parts[1]).name != archive.name:
        raise RuntimeError(f"release sidecar filename mismatch: {parts[1]!r} != {archive.name!r}")
    actual = sha256_file(archive)
    if parts[0].lower() != actual:
        raise RuntimeError(f"release sidecar SHA256 mismatch: expected {parts[0].lower()}, got {actual}")
    return actual


def load_policy(path: Path) -> dict[str, Any]:
    policy = load_json(path)
    if policy.get("schema") != 1 or policy.get("project") != "Crakbit Core":
        raise RuntimeError("unsupported release policy")
    if policy.get("repository") != "navindusasmitha/Crakbit-Core":
        raise RuntimeError("release policy repository identity mismatch")
    return policy


def create_manifest(args: argparse.Namespace) -> int:
    archive = Path(args.archive).resolve()
    sidecar = Path(args.sidecar).resolve() if args.sidecar else archive.with_name(archive.name + ".sha256")
    output = Path(args.output).resolve()
    policy_path = Path(args.policy).resolve()
    if not archive.is_file():
        raise RuntimeError(f"release archive does not exist: {archive}")

    source_commit = args.source_commit.lower()
    if not HEX40.fullmatch(source_commit):
        raise RuntimeError("--source-commit must be exactly 40 hex characters")

    policy = load_policy(policy_path)
    if args.channel not in policy.get("channels", {}):
        raise RuntimeError(f"release channel is not allowed by policy: {args.channel}")

    archive_hash = verify_sidecar(archive, sidecar)
    inspected = inspect_archive(archive)
    build = inspected["build_manifest"]
    if build.get("source_commit") != source_commit:
        raise RuntimeError(
            f"package source_commit mismatch: {build.get('source_commit')!r} != {source_commit!r}"
        )
    channel_policy = policy["channels"][args.channel]
    if bool(channel_policy.get("require_mainnet_disabled", False)) and bool(build.get("mainnet_enabled")):
        raise RuntimeError(f"{args.channel} release policy forbids mainnet-enabled packages")

    manifest = {
        "schema": 1,
        "project": "Crakbit Core",
        "milestone": "CRAK-025",
        "repository": policy["repository"],
        "channel": args.channel,
        "source_commit": source_commit,
        "source_date_epoch": int(build.get("source_date_epoch", -1)),
        "artifact": {
            "archive": archive.name,
            "sha256": archive_hash,
            "size": archive.stat().st_size,
            "sidecar": sidecar.name,
            "sidecar_sha256": sha256_file(sidecar),
        },
        "package": {
            "root": inspected["package_root"],
            "build_manifest_sha256": inspected["build_manifest_sha256"],
            "sha256sums_sha256": inspected["sha256sums_sha256"],
            "verified_internal_files": inspected["verified_internal_files"],
            "build_manifest": build,
        },
        "trust_policy": {
            "github_attestation_required": bool(channel_policy.get("github_attestation_required", False)),
            "offline_operator_signature_required": bool(channel_policy.get("offline_operator_signature_required", False)),
            "operator_signature_algorithm": policy.get("operator_signing", {}).get("algorithm"),
        },
    }
    canonical_write(output, manifest)
    print(f"CRAK-025 release manifest: OK archive={archive.name} sha256={archive_hash} channel={args.channel}")
    return 0


def verify_manifest(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    bundle = Path(args.bundle).resolve()
    manifest = load_json(manifest_path)
    if manifest.get("schema") != 1 or manifest.get("milestone") != "CRAK-025":
        raise RuntimeError("unsupported CRAK-025 release manifest")
    if manifest.get("repository") != "navindusasmitha/Crakbit-Core":
        raise RuntimeError("release manifest repository identity mismatch")

    artifact = manifest.get("artifact", {})
    archive = bundle / str(artifact.get("archive", ""))
    sidecar = bundle / str(artifact.get("sidecar", ""))
    if not archive.is_file() or not sidecar.is_file():
        raise RuntimeError("release bundle is missing archive or SHA256 sidecar")

    actual_archive_hash = verify_sidecar(archive, sidecar)
    if actual_archive_hash != artifact.get("sha256"):
        raise RuntimeError("release archive SHA256 no longer matches RELEASE-MANIFEST.json")
    if archive.stat().st_size != int(artifact.get("size", -1)):
        raise RuntimeError("release archive size no longer matches RELEASE-MANIFEST.json")
    if sha256_file(sidecar) != artifact.get("sidecar_sha256"):
        raise RuntimeError("release sidecar SHA256 no longer matches RELEASE-MANIFEST.json")

    inspected = inspect_archive(archive)
    package = manifest.get("package", {})
    if inspected["build_manifest"] != package.get("build_manifest"):
        raise RuntimeError("package BUILD-MANIFEST.json no longer matches RELEASE-MANIFEST.json")
    if inspected["build_manifest_sha256"] != package.get("build_manifest_sha256"):
        raise RuntimeError("package build-manifest hash mismatch")
    if inspected["sha256sums_sha256"] != package.get("sha256sums_sha256"):
        raise RuntimeError("package SHA256SUMS hash mismatch")
    if inspected["verified_internal_files"] != int(package.get("verified_internal_files", -1)):
        raise RuntimeError("package internal checksum-entry count mismatch")

    print(
        "CRAK-025 release verification: OK "
        f"archive={archive.name} sha256={actual_archive_hash} source={manifest.get('source_commit')}"
    )
    return 0


def run_openssl(argv: list[str], label: str) -> None:
    try:
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except OSError as exc:
        raise RuntimeError("openssl is required for detached Ed25519 signatures") from exc
    if p.returncode != 0:
        out = (p.stdout or "").strip()
        raise RuntimeError(f"{label} failed" + (f": {out}" if out else ""))


def sign_manifest(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest).resolve()
    key = Path(args.private_key).resolve()
    signature = Path(args.signature).resolve()
    if not manifest.is_file():
        raise RuntimeError("release manifest does not exist")
    if not key.is_file():
        raise RuntimeError("operator private key does not exist")
    key_text = key.read_text(encoding="utf-8", errors="ignore")
    if "PRIVATE KEY" not in key_text:
        raise RuntimeError("--private-key does not appear to be a PEM private key")
    signature.parent.mkdir(parents=True, exist_ok=True)
    run_openssl(
        ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(key), "-in", str(manifest), "-out", str(signature)],
        "release signature",
    )
    print(f"CRAK-025 detached signature: OK signature={signature}")
    return 0


def verify_signature(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest).resolve()
    key = Path(args.public_key).resolve()
    signature = Path(args.signature).resolve()
    for p in (manifest, key, signature):
        if not p.is_file():
            raise RuntimeError(f"missing signature-verification input: {p}")
    key_text = key.read_text(encoding="utf-8", errors="ignore")
    if "PUBLIC KEY" not in key_text or "PRIVATE KEY" in key_text:
        raise RuntimeError("--public-key must be a PEM public key, never a private key")
    run_openssl(
        ["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(key), "-in", str(manifest), "-sigfile", str(signature)],
        "release signature verification",
    )
    print(f"CRAK-025 detached signature verification: OK public_key={key.name}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CRAK-025 release trust verifier")
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser("manifest", help="validate a package and create RELEASE-MANIFEST.json")
    m.add_argument("--archive", required=True)
    m.add_argument("--sidecar")
    m.add_argument("--policy", default="release/RELEASE_POLICY.json")
    m.add_argument("--source-commit", required=True)
    m.add_argument("--channel", default="testnet")
    m.add_argument("--output", required=True)
    m.set_defaults(func=create_manifest)

    v = sub.add_parser("verify", help="verify release bundle bytes against RELEASE-MANIFEST.json")
    v.add_argument("--manifest", required=True)
    v.add_argument("--bundle", required=True)
    v.set_defaults(func=verify_manifest)

    s = sub.add_parser("sign", help="create a detached Ed25519 signature using an explicit offline key path")
    s.add_argument("--manifest", required=True)
    s.add_argument("--private-key", required=True)
    s.add_argument("--signature", required=True)
    s.set_defaults(func=sign_manifest)

    sv = sub.add_parser("verify-signature", help="verify a detached Ed25519 release-manifest signature")
    sv.add_argument("--manifest", required=True)
    sv.add_argument("--public-key", required=True)
    sv.add_argument("--signature", required=True)
    sv.set_defaults(func=verify_signature)
    return p


def main() -> int:
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, json.JSONDecodeError, tarfile.TarError) as exc:
        print(f"CRAK-025 release trust: FAILED: {exc}", file=os.sys.stderr)
        raise SystemExit(1)
