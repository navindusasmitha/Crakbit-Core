#!/usr/bin/env python3
"""Materialize pinned Bitcoin Core with Crakbit yespower build wiring.

This stage intentionally does not change consensus hashing yet. It proves that
exact pinned yespower source can be vendored and built as part of Bitcoin Core
before CRAK-005 changes CBlockHeader::GetHash().
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".work"
LOCK = ROOT / "SOURCE_LOCK.json"
BTC = WORK / "bitcoin"
YESPOWER = WORK / "yespower"
OUT = WORK / "crakbit"

YESPOWER_FILES = (
    "yespower-opt.c",
    "yespower-platform.c",
    "yespower.h",
    "sha256.c",
    "sha256.h",
    "sysendian.h",
    "insecure_memzero.h",
    "README",
)


def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def head(repo: Path) -> str:
    return run("git", "rev-parse", "HEAD", cwd=repo)


def require_pinned(repo: Path, expected: str, label: str) -> None:
    if not (repo / ".git").exists():
        raise SystemExit(f"missing {label} checkout at {repo}; run scripts/bootstrap.sh")
    actual = head(repo)
    if actual != expected:
        raise SystemExit(f"{label} pin mismatch: expected {expected}, got {actual}")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one materializer anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    btc_lock = lock["upstreams"]["bitcoin_core"]
    yes_lock = lock["upstreams"]["yespower"]

    require_pinned(BTC, btc_lock["commit_sha"], "Bitcoin Core")
    require_pinned(YESPOWER, yes_lock["commit_sha"], "yespower")

    # bootstrap.sh intentionally uses a partial clone. A local clone of a
    # promisor/partial repository is not portable across Git versions, so use
    # a detached worktree instead. It keeps exact source identity and avoids a
    # second network fetch.
    if OUT.exists():
        shutil.rmtree(OUT)
    run("git", "worktree", "prune", cwd=BTC)
    run(
        "git",
        "worktree",
        "add",
        "--force",
        "--detach",
        str(OUT),
        btc_lock["commit_sha"],
        cwd=BTC,
    )
    if head(OUT) != btc_lock["commit_sha"]:
        raise SystemExit("materialized Bitcoin Core HEAD does not match SOURCE_LOCK.json")

    vendor = OUT / "src" / "crypto" / "yespower"
    vendor.mkdir(parents=True, exist_ok=True)
    for name in YESPOWER_FILES:
        src = YESPOWER / name
        if not src.is_file():
            raise SystemExit(f"required yespower source is missing: {src}")
        shutil.copy2(src, vendor / name)

    yespower_cmake = "\n".join(
        [
            "# Crakbit Core: pinned Openwall yespower build target.",
            "# Source commit is recorded in the repository SOURCE_LOCK.json.",
            "",
            "add_library(crakbit_yespower STATIC EXCLUDE_FROM_ALL",
            "  yespower-opt.c",
            "  sha256.c",
            ")",
            "",
            "target_include_directories(crakbit_yespower PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})",
            "target_link_libraries(crakbit_yespower PRIVATE core_interface)",
            "set_target_properties(crakbit_yespower PROPERTIES C_STANDARD 99 C_STANDARD_REQUIRED YES)",
            "",
        ]
    )
    (vendor / "CMakeLists.txt").write_text(yespower_cmake, encoding="utf-8")

    src_cmake = OUT / "src" / "CMakeLists.txt"
    replace_once(
        src_cmake,
        "add_subdirectory(crypto)\nadd_subdirectory(util)",
        "add_subdirectory(crypto)\nadd_subdirectory(crypto/yespower)\nadd_subdirectory(util)",
    )
    replace_once(
        src_cmake,
        "    bitcoin_crypto\n    secp256k1\n",
        "    bitcoin_crypto\n    crakbit_yespower\n    secp256k1\n",
    )

    manifest = WORK / "materialized-source.txt"
    manifest.write_text(
        "\n".join(
            [
                "project=Crakbit Core",
                "stage=CRAK-004-yespower-build-wiring",
                f"bitcoin_core_commit={btc_lock['commit_sha']}",
                f"yespower_commit={yes_lock['commit_sha']}",
                "yespower_target=crakbit_yespower",
                "consensus_hash_changed=false",
                "mainnet_enabled=false",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"materialized: {OUT}")
    print(f"bitcoin:      {btc_lock['commit_sha']}")
    print(f"yespower:     {yes_lock['commit_sha']}")
    print("stage:        build wiring only; consensus hash unchanged")


if __name__ == "__main__":
    main()
