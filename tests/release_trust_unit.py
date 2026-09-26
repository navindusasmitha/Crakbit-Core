#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "release-trust.py"
POLICY = ROOT / "release" / "RELEASE_POLICY.json"
SOURCE = "a" * 40
EPOCH = 1700000000
ARCHIVE_NAME = "crakbit-core-unit-testnet-linux-x86_64.tar.gz"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run(argv: list[str], *, ok: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if ok and p.returncode != 0:
        raise AssertionError(f"command failed ({p.returncode}): {' '.join(argv)}\n{p.stdout}")
    if not ok and p.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {' '.join(argv)}\n{p.stdout}")
    return p


def seed_release(bundle: Path) -> tuple[Path, Path]:
    bundle.mkdir(parents=True)
    stage = bundle / "stage"
    pkg = stage / "crakbit-core-unit-testnet-linux-x86_64"
    (pkg / "bin").mkdir(parents=True)
    (pkg / "share" / "doc" / "crakbit-core").mkdir(parents=True)

    files = {
        "bin/crakbitd": b"daemon\n",
        "bin/crakbit-cli": b"cli\n",
        "bin/crakminer-scan": b"scanner\n",
    }
    for rel, data in files.items():
        path = pkg / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    build_manifest = {
        "schema": 1,
        "project": "Crakbit Core",
        "package_version": "unit-testnet",
        "platform": "linux",
        "arch": "x86_64",
        "source_commit": SOURCE,
        "source_date_epoch": EPOCH,
        "mainnet_enabled": False,
        "upstreams": {
            "bitcoin_core_commit": "b" * 40,
            "yespower_commit": "c" * 40,
        },
        "pow": {"name": "yespower", "version": "1.0", "N": 2048, "r": 8},
    }
    build_path = pkg / "share" / "doc" / "crakbit-core" / "BUILD-MANIFEST.json"
    build_path.write_text(json.dumps(build_manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    checksum_paths = [pkg / rel for rel in files] + [build_path]
    lines = []
    for path in sorted(checksum_paths, key=lambda p: p.relative_to(pkg).as_posix()):
        rel = path.relative_to(pkg).as_posix()
        lines.append(f"{sha256_file(path)}  {rel}\n")
    (pkg / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")

    archive = bundle / ARCHIVE_NAME
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(pkg, arcname=pkg.name)
    sidecar = bundle / f"{ARCHIVE_NAME}.sha256"
    sidecar.write_text(f"{sha256_file(archive)}  {ARCHIVE_NAME}\n", encoding="utf-8")
    shutil.rmtree(stage)
    return archive, sidecar


def create_manifest(bundle: Path, archive: Path) -> Path:
    manifest = bundle / "RELEASE-MANIFEST.json"
    run(
        [
            "python3",
            str(TOOL),
            "manifest",
            "--archive",
            str(archive),
            "--policy",
            str(POLICY),
            "--source-commit",
            SOURCE,
            "--channel",
            "testnet",
            "--output",
            str(manifest),
        ]
    )
    return manifest


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bundle = tmp / "release"
        archive, sidecar = seed_release(bundle)
        manifest = create_manifest(bundle, archive)

        good = run(["python3", str(TOOL), "verify", "--manifest", str(manifest), "--bundle", str(bundle)])
        assert "release verification: OK" in good.stdout

        # Sidecar tampering must fail even when archive bytes are untouched.
        original_sidecar = sidecar.read_bytes()
        sidecar.write_text(f"{'0' * 64}  {ARCHIVE_NAME}\n", encoding="utf-8")
        bad_sidecar = run(
            ["python3", str(TOOL), "verify", "--manifest", str(manifest), "--bundle", str(bundle)],
            ok=False,
        )
        assert "sidecar SHA256 mismatch" in bad_sidecar.stdout
        sidecar.write_bytes(original_sidecar)

        # Archive mutation must fail against both the sidecar and manifest trust chain.
        original_archive = archive.read_bytes()
        archive.write_bytes(original_archive + b"tampered")
        bad_archive = run(
            ["python3", str(TOOL), "verify", "--manifest", str(manifest), "--bundle", str(bundle)],
            ok=False,
        )
        assert "sidecar SHA256 mismatch" in bad_archive.stdout
        archive.write_bytes(original_archive)

        # Test the detached Ed25519 protocol using ephemeral CI-only keys. The
        # private key exists only inside this temporary directory.
        private_key = tmp / "ephemeral-private.pem"
        public_key = tmp / "ephemeral-public.pem"
        signature = bundle / "RELEASE-MANIFEST.json.sig"
        run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)])
        run(["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)])
        run(
            [
                "python3",
                str(TOOL),
                "sign",
                "--manifest",
                str(manifest),
                "--private-key",
                str(private_key),
                "--signature",
                str(signature),
            ]
        )
        signed = run(
            [
                "python3",
                str(TOOL),
                "verify-signature",
                "--manifest",
                str(manifest),
                "--public-key",
                str(public_key),
                "--signature",
                str(signature),
            ]
        )
        assert "signature verification: OK" in signed.stdout

        original_manifest = manifest.read_bytes()
        manifest.write_bytes(original_manifest + b" \n")
        bad_sig = run(
            [
                "python3",
                str(TOOL),
                "verify-signature",
                "--manifest",
                str(manifest),
                "--public-key",
                str(public_key),
                "--signature",
                str(signature),
            ],
            ok=False,
        )
        assert "signature verification failed" in bad_sig.stdout
        manifest.write_bytes(original_manifest)

        # A private key must never be accepted in the public-key verifier slot.
        private_as_public = run(
            [
                "python3",
                str(TOOL),
                "verify-signature",
                "--manifest",
                str(manifest),
                "--public-key",
                str(private_key),
                "--signature",
                str(signature),
            ],
            ok=False,
        )
        assert "never a private key" in private_as_public.stdout

    print("CRAK-025 release trust unit: OK")


if __name__ == "__main__":
    main()
