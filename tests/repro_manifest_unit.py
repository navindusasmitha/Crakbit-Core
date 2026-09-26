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
TOOL = ROOT / "scripts" / "repro-manifest.py"
SOURCE = "a" * 40
EPOCH = 1700000000
ARCHIVE_NAME = "crakbit-core-unit-linux-x86_64.tar.gz"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(*args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(
        ["python3", str(TOOL), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if ok and p.returncode != 0:
        raise AssertionError(f"command failed ({p.returncode}): {p.stdout}")
    if not ok and p.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {p.stdout}")
    return p


def seed_bundle(bundle: Path) -> None:
    (bundle / "bin").mkdir(parents=True)
    for name, payload in {
        "crakbitd": b"daemon-bytes\n",
        "crakbit-cli": b"cli-bytes\n",
        "crakminer-scan": b"scanner-bytes\n",
    }.items():
        (bundle / "bin" / name).write_bytes(payload)

    staging = bundle.parent / "stage"
    pkg_root = staging / "crakbit-core-unit-linux-x86_64"
    manifest_dir = pkg_root / "share" / "doc" / "crakbit-core"
    manifest_dir.mkdir(parents=True)
    build_manifest = {
        "schema": 1,
        "project": "Crakbit Core",
        "package_version": "unit",
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
    (manifest_dir / "BUILD-MANIFEST.json").write_text(
        json.dumps(build_manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    archive = bundle / ARCHIVE_NAME
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(pkg_root, arcname=pkg_root.name)
    shutil.rmtree(staging)
    (bundle / f"{ARCHIVE_NAME}.sha256").write_text(
        f"{sha256(archive)}  {ARCHIVE_NAME}\n", encoding="utf-8"
    )


def create(bundle: Path, builder: str) -> None:
    run(
        "create",
        "--bundle",
        str(bundle),
        "--builder-id",
        builder,
        "--runner-label",
        f"unit-{builder}",
        "--source-commit",
        SOURCE,
        "--source-date-epoch",
        str(EPOCH),
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        a = tmp / "builder-a"
        b = tmp / "builder-b"
        seed_bundle(a)
        shutil.copytree(a, b)

        create(a, "builder-a")
        create(b, "builder-b")
        good = run("compare", "--left", str(a), "--right", str(b))
        assert "reproducibility: OK" in good.stdout

        # A byte mutation after manifest creation must be detected even if the
        # deterministic JSON manifests still match.
        (b / "bin" / "crakbit-cli").write_bytes(b"tampered\n")
        bad = run("compare", "--left", str(a), "--right", str(b), ok=False)
        assert "SHA256 mismatch" in bad.stdout

        # Restore the bundle, then prove that two lanes cannot masquerade as
        # independent builders by using the same builder identity.
        shutil.rmtree(b)
        shutil.copytree(a, b)
        for generated in ("REPRODUCIBILITY-MANIFEST.json", "BUILDER-INFO.json"):
            (b / generated).unlink(missing_ok=True)
        create(b, "builder-a")
        same = run("compare", "--left", str(a), "--right", str(b), ok=False)
        assert "builder IDs must differ" in same.stdout

        # Package sidecar corruption must fail at collection time.
        c = tmp / "builder-c"
        seed_bundle(c)
        (c / f"{ARCHIVE_NAME}.sha256").write_text(
            f"{'0' * 64}  {ARCHIVE_NAME}\n", encoding="utf-8"
        )
        sidecar = run(
            "create",
            "--bundle",
            str(c),
            "--builder-id",
            "builder-c",
            "--source-commit",
            SOURCE,
            "--source-date-epoch",
            str(EPOCH),
            ok=False,
        )
        assert "sidecar mismatch" in sidecar.stdout

    print("CRAK-024 reproducibility manifest unit: OK")


if __name__ == "__main__":
    main()
