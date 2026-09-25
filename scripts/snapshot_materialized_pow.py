#!/usr/bin/env python3
"""Print exact final-Core PoW contexts before CRAK-004/005 rewires them."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE = ROOT / ".work" / "crakbit-source" / "build" / "wam-core"

ANCHORS = {
    "src/validation.cpp": [
        "WAM_RANDOMX_POW_VERIFIED",
        "HasValidProofOfWork",
        "CheckBlockHeader",
        "CheckProofOfWork(",
    ],
    "src/rpc/mining.cpp": [
        "randomx_seedhash",
        "WAM_MINER_USES_RANDOMX",
        "GetRandomXPoWHash",
    ],
    "src/Makefile.am": [
        "wam/crypto/randomx_hash.cpp",
        "wam/crypto/randomx_hash.h",
    ],
    "src/wam/crypto/randomx_hash.cpp": [
        "GetRandomXPoWHash",
        "randomx_calculate_hash",
    ],
}


def print_context(path: Path, needle: str, radius: int) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [i for i, line in enumerate(lines) if needle in line]
    if not hits:
        return 0
    for idx in hits:
        lo = max(0, idx - radius)
        hi = min(len(lines), idx + radius + 1)
        print(f"\n## {path.relative_to(path.parents[2])} lines {lo+1}-{hi} (anchor {idx+1}: {needle})")
        for n in range(lo, hi):
            mark = ">" if n == idx else " "
            print(f"{mark}{n+1:6}: {lines[n]}")
    return len(hits)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", type=Path, default=DEFAULT_CORE)
    ap.add_argument("--radius", type=int, default=12)
    args = ap.parse_args()
    core = args.core.resolve()
    if not (core / "src/validation.cpp").exists():
        raise SystemExit(f"materialized Core tree not found: {core}")

    total = 0
    for rel, needles in ANCHORS.items():
        path = core / rel
        if not path.exists():
            print(f"\n## missing {rel}")
            continue
        for needle in needles:
            total += print_context(path, needle, args.radius)

    print(f"\nMATERIALIZED_POW_CONTEXT anchors={total}")
    if total < 8:
        raise SystemExit("too few PoW anchors found; final Core layout changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
