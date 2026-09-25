#!/usr/bin/env python3
"""Print narrow source context around consensus-critical PoW markers.

This is a migration aid for CRAK-004/005. It deliberately avoids dumping the
whole inherited tree: only exact RandomX/PoW/build anchors plus surrounding
lines are emitted so reviewed transformations can be strict.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / ".work" / "crakbit-source"

MARKERS = (
    "WAM_RANDOMX_POW_VERIFIED",
    "GetRandomXPoWHash",
    "GetRandomXSeedHash",
    "WAM_MINER_USES_RANDOMX",
    "HasValidProofOfWork",
    "CheckProofOfWork(block.GetHash()",
    "CheckProofOfWork(pindexNew->GetBlockHash()",
    "randomx_hash.cpp",
    "randomx_hash.h",
)

SUFFIXES = {".cpp", ".cc", ".c", ".h", ".hpp", ".am", ".mk", ".in"}


def emit(path: Path, lineno: int, lines: list[str], radius: int = 12) -> None:
    lo = max(1, lineno - radius)
    hi = min(len(lines), lineno + radius)
    print(f"\n## {path} lines {lo}-{hi} (anchor {lineno})")
    for n in range(lo, hi + 1):
        flag = ">" if n == lineno else " "
        print(f"{flag}{n:5}: {lines[n - 1]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = ap.parse_args()
    tree = args.tree.resolve()
    if not (tree / "src").is_dir():
        raise SystemExit(f"missing prepared tree: {tree}")

    seen: set[tuple[str, int]] = set()
    hits = 0
    for file in sorted(tree.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in SUFFIXES:
            continue
        rel = file.relative_to(tree)
        if any(part in {".git", "depends", "node_modules", "build"} for part in rel.parts):
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            if any(m in line for m in MARKERS):
                key = (str(rel), i)
                if key in seen:
                    continue
                seen.add(key)
                emit(rel, i, lines)
                hits += 1
    print(f"\nPOW_CONTEXT anchors={hits}")
    if hits < 5:
        raise SystemExit("POW_CONTEXT: too few expected anchors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
