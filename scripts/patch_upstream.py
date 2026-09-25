#!/usr/bin/env python3
"""Crakbit migration patch manifest and staging helper.

This intentionally separates *describing* consensus changes from applying them.
`--list` is always safe. `--check-tree` validates that the pinned WAM-derived
working tree has the expected high-level layout. `--stage-overlay` copies the
Crakbit-owned overlay into that disposable tree but does not yet modify Bitcoin
Core validation paths; those anchored transformations are added as reviewed
patch IDs in later revisions.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / ".work" / "crakbit-source"

PATCHES = [
    ("CRAK-000", "Install Crakbit-owned source overlay and constants", True),
    ("CRAK-001", "Remove WAM founder reserve / spendable-genesis paths", True),
    ("CRAK-002", "Remove WAM treasury/dev-fee consensus enforcement", True),
    ("CRAK-003", "Set 5 CRAK subsidy, 2,100,000-block halvings, 21M ceiling", True),
    ("CRAK-004", "Replace RandomX PoW comparison with yespower 1.0", True),
    ("CRAK-005", "Retain SHA256d block IDs; yespower only checks nBits target", True),
    ("CRAK-006", "Retune DGW3 for 60-second spacing and add vectors", True),
    ("CRAK-007", "Replace WAM network IDs, ports, prefixes, seeds and genesis", True),
    ("CRAK-008", "Expose Crakbit PoW/network RPC metadata", False),
    ("CRAK-009", "Rename packaging/config/binaries to Crakbit", False),
]

REQUIRED_PATHS = [
    "src/wam",
    "scripts",
    "genesis",
    "pool",
    "explorer",
]


def list_patches() -> None:
    for pid, desc, consensus in PATCHES:
        flag = "consensus" if consensus else "non-consensus"
        print(f"{pid}  [{flag}]  {desc}")


def check_tree(tree: Path) -> None:
    missing = [p for p in REQUIRED_PATHS if not (tree / p).exists()]
    if missing:
        raise SystemExit("unexpected WAM-derived tree; missing: " + ", ".join(missing))
    print(f"source tree layout: PASS ({tree})")


def stage_overlay(tree: Path) -> None:
    check_tree(tree)
    src = ROOT / "src" / "crakbit"
    dst = tree / "src" / "crakbit"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"staged Crakbit overlay: {dst}")
    print("NOTE: consensus validation paths are not modified by this command yet.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--check-tree", action="store_true")
    g.add_argument("--stage-overlay", action="store_true")
    args = ap.parse_args()

    if args.list:
        list_patches()
    elif args.check_tree:
        check_tree(args.tree)
    else:
        stage_overlay(args.tree)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
