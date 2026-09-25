#!/usr/bin/env python3
"""Inventory consensus/build PoW hooks in the prepared pinned source tree.

Read-only diagnostic used while implementing CRAK-004/005. It deliberately
prints file:line anchors for RandomX, PoW hash selection, target checks, and
build integration so the migration patch never guesses at consensus code.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / ".work" / "crakbit-source"

PATTERNS = re.compile(
    r"randomx|RandomX|GetPoWHash|GetHash\s*\(|CheckProofOfWork|"
    r"CheckProofOfWorkImpl|powhash|pow_hash|proof.?of.?work|"
    r"WAM_RANDOMX|randomx_hash|randomx_seed|high-hash|"
    r"CBlockHeader|SerializeHash|yespower|CMakeLists|Makefile",
    re.I,
)

TEXT_SUFFIXES = {
    ".cpp", ".cc", ".c", ".h", ".hpp", ".in", ".am", ".mk", ".cmake",
    ".py", ".sh", ".txt", ".md",
}

SKIP_DIRS = {".git", "depends", "node_modules", "build", "qa-assets"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = ap.parse_args()
    tree = args.tree.resolve()
    if not (tree / "src").exists():
        raise SystemExit(f"missing prepared source tree: {tree}")

    files = 0
    matches = 0
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(tree).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hit_lines = []
        for lineno, line in enumerate(text.splitlines(), 1):
            if PATTERNS.search(line):
                hit_lines.append((lineno, line.rstrip()))
        if not hit_lines:
            continue
        files += 1
        rel = path.relative_to(tree)
        print(f"\n## {rel}")
        for lineno, line in hit_lines[:160]:
            print(f"{lineno}: {line}")
            matches += 1
        if len(hit_lines) > 160:
            print(f"... {len(hit_lines) - 160} more matches omitted")
            matches += len(hit_lines) - 160

    print(f"\nPOW_INVENTORY files={files} matches={matches}")
    if matches == 0:
        raise SystemExit("POW_INVENTORY: no PoW markers found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
