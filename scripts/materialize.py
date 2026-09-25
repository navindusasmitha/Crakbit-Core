#!/usr/bin/env python3
"""Materialize pinned Bitcoin Core with Crakbit yespower consensus hashing.

CRAK-004 vendors and builds the exact pinned yespower source. CRAK-005 changes
CBlockHeader::GetHash() to hash the canonical serialized 80-byte header using
the consensus-locked Crakbit yespower profile. There is deliberately no
SHA256d fallback on yespower failure.
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
VECTOR_PROBE = ROOT / "tests" / "yespower_vector.c"
HEADER_PROBE = ROOT / "tests" / "block_hash_vector.cpp"

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


def apply_block_hash_patch(tree: Path) -> None:
    block_cpp = tree / "src" / "primitives" / "block.cpp"

    replace_once(
        block_cpp,
        "#include <hash.h>\n#include <tinyformat.h>",
        "#include <crypto/yespower/yespower.h>\n#include <streams.h>\n#include <tinyformat.h>",
    )
    replace_once(
        block_cpp,
        "#include <memory>\n#include <span>",
        "#include <cstdlib>\n#include <memory>\n#include <span>",
    )
    replace_once(
        block_cpp,
        """uint256 CBlockHeader::GetHash() const
{
    return (HashWriter{} << *this).GetHash();
}
""",
        """uint256 CBlockHeader::GetHash() const
{
    DataStream stream{};
    stream << *this;

    // Consensus invariant: a Bitcoin-style block header is exactly 80 bytes.
    // Hash the canonical serialization, never the in-memory C++ object layout.
    if (stream.size() != 80) {
        std::abort();
    }

    static constexpr unsigned char PERS[] = "Crakbit-Core-v0.1";
    const yespower_params_t params{
        YESPOWER_1_0,
        2048,
        8,
        reinterpret_cast<const uint8_t*>(PERS),
        sizeof(PERS) - 1,
    };

    yespower_binary_t out{};
    if (yespower_tls(
            reinterpret_cast<const uint8_t*>(stream.data()),
            stream.size(),
            &params,
            &out) != 0) {
        // Consensus code must never silently fall back to another hash or a
        // fabricated value. A local allocation/hash failure is fatal.
        std::abort();
    }

    return uint256{std::span<const unsigned char>{out.uc, sizeof(out.uc)}};
}
""",
    )


def main() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    btc_lock = lock["upstreams"]["bitcoin_core"]
    yes_lock = lock["upstreams"]["yespower"]

    require_pinned(BTC, btc_lock["commit_sha"], "Bitcoin Core")
    require_pinned(YESPOWER, yes_lock["commit_sha"], "yespower")
    for probe in (VECTOR_PROBE, HEADER_PROBE):
        if not probe.is_file():
            raise SystemExit(f"missing Crakbit vector probe: {probe}")

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
    shutil.copy2(VECTOR_PROBE, vendor / "crakbit-vector.c")
    shutil.copy2(HEADER_PROBE, vendor / "crakbit-header-vector.cpp")

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
            "add_executable(crakbit_yespower_vector EXCLUDE_FROM_ALL crakbit-vector.c)",
            "target_link_libraries(crakbit_yespower_vector PRIVATE crakbit_yespower)",
            "set_target_properties(crakbit_yespower_vector PROPERTIES C_STANDARD 99 C_STANDARD_REQUIRED YES)",
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
    replace_once(
        src_cmake,
        """target_link_libraries(bitcoin_consensus
  PRIVATE
    core_interface
    bitcoin_crypto
    crakbit_yespower
    secp256k1
)
""",
        """target_link_libraries(bitcoin_consensus
  PRIVATE
    core_interface
    bitcoin_crypto
    crakbit_yespower
    secp256k1
)

add_executable(crakbit_header_hash_vector EXCLUDE_FROM_ALL
  crypto/yespower/crakbit-header-vector.cpp
)
target_link_libraries(crakbit_header_hash_vector PRIVATE bitcoin_consensus)
""",
    )

    apply_block_hash_patch(OUT)

    manifest = WORK / "materialized-source.txt"
    manifest.write_text(
        "\n".join(
            [
                "project=Crakbit Core",
                "stage=CRAK-005-yespower-block-identity",
                f"bitcoin_core_commit={btc_lock['commit_sha']}",
                f"yespower_commit={yes_lock['commit_sha']}",
                "yespower_target=crakbit_yespower",
                "yespower_vector_input=000102...4f",
                "block_header_serialized_bytes=80",
                "block_identity_hash=yespower",
                "consensus_hash_changed=true",
                "mainnet_enabled=false",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"materialized: {OUT}")
    print(f"bitcoin:      {btc_lock['commit_sha']}")
    print(f"yespower:     {yes_lock['commit_sha']}")
    print("stage:        CRAK-005 yespower block identity enabled")


if __name__ == "__main__":
    main()
