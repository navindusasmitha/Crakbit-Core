#!/usr/bin/env python3
"""CRAK-024 deterministic build-manifest collection and cross-builder comparison.

The deterministic manifest intentionally excludes machine-specific provenance so two
independent builders can be compared byte-for-byte. Builder metadata is written to a
separate file and is required to identify different builder lanes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import tarfile
from pathlib import Path
from typing import Any

DETERMINISTIC_MANIFEST = "REPRODUCIBILITY-MANIFEST.json"
BUILDER_INFO = "BUILDER-INFO.json"
REQUIRED_BINARIES = ("crakbitd", "crakbit-cli", "crakminer-scan")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def command_version(argv: list[str]) -> str | None:
    try:
        p = subprocess.run(argv, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError:
        return None
    text = (p.stdout or "").strip()
    return text.splitlines()[0] if text else None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_write(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def only_archive(bundle: Path) -> Path:
    archives = sorted(bundle.glob("crakbit-core-*-linux-*.tar.gz"))
    if len(archives) != 1:
        raise RuntimeError(f"expected exactly one Crakbit Linux archive in {bundle}, found {len(archives)}")
    return archives[0]


def package_build_manifest(archive: Path) -> dict[str, Any]:
    with tarfile.open(archive, mode="r:gz") as tf:
        matches = [m for m in tf.getmembers() if m.name.endswith("/share/doc/crakbit-core/BUILD-MANIFEST.json")]
        if len(matches) != 1:
            raise RuntimeError(f"expected one BUILD-MANIFEST.json in {archive.name}, found {len(matches)}")
        extracted = tf.extractfile(matches[0])
        if extracted is None:
            raise RuntimeError("unable to read BUILD-MANIFEST.json from archive")
        return json.loads(extracted.read().decode("utf-8"))


def verify_sidecar(archive: Path) -> Path:
    sidecar = archive.with_name(archive.name + ".sha256")
    if not sidecar.is_file():
        raise RuntimeError(f"missing package SHA256 sidecar: {sidecar.name}")
    parts = sidecar.read_text(encoding="utf-8").strip().split()
    if len(parts) < 2:
        raise RuntimeError(f"invalid SHA256 sidecar: {sidecar.name}")
    expected = parts[0].lower()
    actual = sha256_file(archive)
    if expected != actual:
        raise RuntimeError(f"package sidecar mismatch for {archive.name}: expected {expected}, got {actual}")
    return sidecar


def artifact_entry(path: Path) -> dict[str, Any]:
    return {"sha256": sha256_file(path), "size": path.stat().st_size}


def create_manifest(args: argparse.Namespace) -> int:
    bundle = Path(args.bundle).resolve()
    if not bundle.is_dir():
        raise RuntimeError(f"bundle directory does not exist: {bundle}")

    source_commit = args.source_commit.lower()
    if not HEX40.fullmatch(source_commit):
        raise RuntimeError("--source-commit must be exactly 40 lowercase/uppercase hex characters")
    if args.source_date_epoch < 0:
        raise RuntimeError("--source-date-epoch must be non-negative")
    if not args.builder_id.strip():
        raise RuntimeError("--builder-id must not be empty")

    bin_dir = bundle / "bin"
    files: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_BINARIES:
        path = bin_dir / name
        if not path.is_file():
            raise RuntimeError(f"missing required reproducibility binary: bin/{name}")
        files[f"bin/{name}"] = artifact_entry(path)

    archive = only_archive(bundle)
    sidecar = verify_sidecar(archive)
    files[archive.name] = artifact_entry(archive)
    files[sidecar.name] = artifact_entry(sidecar)

    build_manifest = package_build_manifest(archive)
    if build_manifest.get("source_commit") != source_commit:
        raise RuntimeError(
            f"package source_commit mismatch: {build_manifest.get('source_commit')!r} != {source_commit!r}"
        )
    if int(build_manifest.get("source_date_epoch", -1)) != args.source_date_epoch:
        raise RuntimeError(
            "package source_date_epoch mismatch: "
            f"{build_manifest.get('source_date_epoch')!r} != {args.source_date_epoch!r}"
        )

    deterministic = {
        "schema": 1,
        "project": "Crakbit Core",
        "milestone": "CRAK-024",
        "source_commit": source_commit,
        "source_date_epoch": args.source_date_epoch,
        "package": {
            "archive": archive.name,
            "build_manifest": build_manifest,
        },
        "artifacts": files,
    }
    canonical_write(bundle / DETERMINISTIC_MANIFEST, deterministic)

    builder = {
        "schema": 1,
        "project": "Crakbit Core",
        "milestone": "CRAK-024",
        "builder_id": args.builder_id,
        "runner_label": args.runner_label,
        "runner_name": os.environ.get("RUNNER_NAME"),
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "toolchain": {
            "cc": command_version(["cc", "--version"]),
            "cxx": command_version(["c++", "--version"]),
            "cmake": command_version(["cmake", "--version"]),
            "python": platform.python_version(),
        },
    }
    canonical_write(bundle / BUILDER_INFO, builder)

    print(
        f"CRAK-024 manifest: OK builder={args.builder_id} "
        f"archive={archive.name} sha256={files[archive.name]['sha256']}"
    )
    return 0


def verify_bundle_against_manifest(bundle: Path, manifest: dict[str, Any]) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise RuntimeError(f"{bundle}: manifest artifacts are missing")
    for rel, expected in artifacts.items():
        path = bundle / rel
        if not path.is_file():
            raise RuntimeError(f"{bundle}: missing manifest artifact {rel}")
        actual_hash = sha256_file(path)
        actual_size = path.stat().st_size
        if expected.get("sha256") != actual_hash:
            raise RuntimeError(f"{bundle}: SHA256 mismatch for {rel}")
        if int(expected.get("size", -1)) != actual_size:
            raise RuntimeError(f"{bundle}: size mismatch for {rel}")


def compare(args: argparse.Namespace) -> int:
    left = Path(args.left).resolve()
    right = Path(args.right).resolve()
    for bundle in (left, right):
        if not bundle.is_dir():
            raise RuntimeError(f"builder bundle does not exist: {bundle}")
        if not (bundle / DETERMINISTIC_MANIFEST).is_file():
            raise RuntimeError(f"missing {DETERMINISTIC_MANIFEST} in {bundle}")
        if not (bundle / BUILDER_INFO).is_file():
            raise RuntimeError(f"missing {BUILDER_INFO} in {bundle}")

    lm = load_json(left / DETERMINISTIC_MANIFEST)
    rm = load_json(right / DETERMINISTIC_MANIFEST)
    li = load_json(left / BUILDER_INFO)
    ri = load_json(right / BUILDER_INFO)

    left_id = str(li.get("builder_id", ""))
    right_id = str(ri.get("builder_id", ""))
    if not left_id or not right_id:
        raise RuntimeError("both builder provenance files must include builder_id")
    if left_id == right_id:
        raise RuntimeError(f"independent builder IDs must differ; both are {left_id!r}")

    verify_bundle_against_manifest(left, lm)
    verify_bundle_against_manifest(right, rm)

    if lm != rm:
        keys = sorted(set(lm) | set(rm))
        differing = [k for k in keys if lm.get(k) != rm.get(k)]
        raise RuntimeError(
            "independent builder outputs are not reproducible; deterministic manifest differs at: "
            + ", ".join(differing)
        )

    for rel in sorted(lm["artifacts"]):
        lp = left / rel
        rp = right / rel
        if lp.read_bytes() != rp.read_bytes():
            raise RuntimeError(f"byte comparison failed despite manifest equality: {rel}")

    archive_name = lm["package"]["archive"]
    archive_hash = lm["artifacts"][archive_name]["sha256"]
    print(
        "CRAK-024 independent cross-builder reproducibility: OK "
        f"builders={left_id},{right_id} source={lm['source_commit']} "
        f"archive_sha256={archive_hash} artifacts={len(lm['artifacts'])}"
    )
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CRAK-024 reproducibility manifest/compare helper")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create", help="create deterministic artifact manifest and builder provenance")
    c.add_argument("--bundle", required=True)
    c.add_argument("--builder-id", required=True)
    c.add_argument("--runner-label", default="unknown")
    c.add_argument("--source-commit", required=True)
    c.add_argument("--source-date-epoch", required=True, type=int)
    c.set_defaults(func=create_manifest)

    cmp_p = sub.add_parser("compare", help="verify two independent builder bundles are byte-identical")
    cmp_p.add_argument("--left", required=True)
    cmp_p.add_argument("--right", required=True)
    cmp_p.set_defaults(func=compare)
    return p


def main() -> int:
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"CRAK-024 reproducibility: FAILED: {exc}", file=os.sys.stderr)
        raise SystemExit(1)
