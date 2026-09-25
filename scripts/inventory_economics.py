#!/usr/bin/env python3
"""Inventory inherited monetary-policy hooks in the pinned base source.

This is deliberately read-only. It prints file/line matches for founder,
premine, treasury/dev-fee and vesting logic so consensus edits can be anchored
against the exact pinned source instead of guessed.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / ".work" / "crakbit-source"
PATTERN = re.compile(r"founder|premine|treasury|dev[_-]?fee|devfee|vesting|tranche", re.I)
TEXT_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp", ".py", ".js", ".json", ".md", ".txt"}
SKIP_PARTS = {".git", "node_modules", "build", "depends"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = ap.parse_args()
    tree = args.tree.resolve()
    if not tree.exists():
        raise SystemExit(f"missing source tree: {tree}")

    matches = 0
    files = 0
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
        except UnicodeDecodeError:
            continue
        local = []
        for lineno, line in enumerate(lines, 1):
            if PATTERN.search(line):
                local.append((lineno, line.rstrip()))
        if not local:
            continue
        files += 1
        rel = path.relative_to(tree)
        print(f"\n## {rel}")
        for lineno, line in local:
            matches += 1
            print(f"{lineno}: {line}")

    print(f"\nECONOMICS_INVENTORY files={files} matches={matches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
