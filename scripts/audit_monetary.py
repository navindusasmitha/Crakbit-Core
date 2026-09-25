#!/usr/bin/env python3
"""Audit CRAK-003 directly from the transformed C++ constants."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / ".work" / "crakbit-source"
COIN = 100_000_000


def constant(text: str, name: str) -> str:
    m = re.search(rf"static\s+constexpr\s+(?:int|int64_t)\s+{re.escape(name)}\s*=\s*(.+?)\s*;", text)
    if not m:
        raise SystemExit(f"MONETARY AUDIT FAIL: missing {name}")
    return m.group(1).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = ap.parse_args()
    tree = args.tree.resolve()
    marker = tree / ".crakbit-monetary"
    if not marker.exists():
        raise SystemExit("MONETARY AUDIT FAIL: CRAK-003 marker missing")

    text = (tree / "src/wam/wam-params.h").read_text(encoding="utf-8")
    expected = {
        "WAM_COIN": "100'000'000",
        "WAM_DECIMALS": "8",
        "WAM_MAX_MONEY": "21'000'000 * WAM_COIN",
        "WAM_GENESIS_PREMINE": "0",
        "WAM_MINING_ALLOCATION": "WAM_MAX_MONEY",
        "WAM_INITIAL_BLOCK_SUBSIDY": "5 * WAM_COIN",
        "WAM_SUBSIDY_HALVING_INTERVAL": "2'100'000",
        "WAM_MAX_HALVINGS": "29",
        "WAM_COINBASE_MATURITY": "100",
    }
    for name, want in expected.items():
        got = constant(text, name)
        if got != want:
            raise SystemExit(f"MONETARY AUDIT FAIL: {name}={got!r}, expected {want!r}")

    subsidy = 5 * COIN
    interval = 2_100_000
    total = 0
    epochs = 0
    while subsidy > 0:
        total += subsidy * interval
        subsidy //= 2
        epochs += 1

    terminal = 2_099_999_972_700_000
    ceiling = 21_000_000 * COIN
    if epochs != 29:
        raise SystemExit(f"MONETARY AUDIT FAIL: non-zero epochs={epochs}, expected 29")
    if total != terminal:
        raise SystemExit(f"MONETARY AUDIT FAIL: terminal base units={total}, expected {terminal}")
    if total > ceiling:
        raise SystemExit("MONETARY AUDIT FAIL: terminal issuance exceeds 21M ceiling")

    print("CRAK-003 audit: 5 CRAK initial subsidy")
    print("CRAK-003 audit: 2,100,000-block halving interval")
    print("CRAK-003 audit: 21,000,000 CRAK hard ceiling")
    print("CRAK-003 audit: 100-block coinbase maturity")
    print("terminal issuance: 20,999,999.72700000 CRAK")
    print("MONETARY AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
