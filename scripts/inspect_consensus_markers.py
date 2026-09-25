#!/usr/bin/env python3
"""Print tightly-scoped source context around inherited consensus markers."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / ".work" / "crakbit-source"
MARKERS = [
    "WAM_DEVFEE_ENFORCED",
    "WAM_COINBASE_PAYS_TREASURY",
    "WAM_GBT_DEVFEE",
    "WAM_GENESIS",
    "CheckDevFeeOutput",
    "GetDevFeeAmount",
    "BuildGenesisOutputs",
]
SUFFIXES = {".cpp", ".h", ".hpp", ".cc"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    ap.add_argument("--radius", type=int, default=18)
    args = ap.parse_args()
    tree = args.tree.resolve()
    hits = 0
    for path in sorted(tree.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES or ".git" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        idxs = [i for i, line in enumerate(lines) if any(m in line for m in MARKERS)]
        if not idxs:
            continue
        # Merge nearby windows.
        windows = []
        for i in idxs:
            a, b = max(0, i - args.radius), min(len(lines), i + args.radius + 1)
            if windows and a <= windows[-1][1]:
                windows[-1] = (windows[-1][0], max(windows[-1][1], b))
            else:
                windows.append((a, b))
        print(f"\n===== {path.relative_to(tree)} =====")
        for a, b in windows:
            hits += 1
            print(f"--- lines {a+1}-{b} ---")
            for n in range(a, b):
                print(f"{n+1:5}: {lines[n]}")
    print(f"\nCONSENSUS_MARKER_WINDOWS={hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
