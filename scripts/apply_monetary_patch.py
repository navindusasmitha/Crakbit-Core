#!/usr/bin/env python3
"""Apply CRAK-003 monetary constants to the pinned disposable source tree.

Final v0.1 monetary policy:
- 8 decimals
- 21,000,000 CRAK hard ceiling
- 0 premine
- 5 CRAK initial subsidy
- 2,100,000-block halving interval
- 29 non-zero subsidy epochs
- 100-block coinbase maturity

Integer base-unit halvings produce exactly 20,999,999.72700000 CRAK.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / ".work" / "crakbit-source"


class PatchError(RuntimeError):
    pass


def replace_constant(text: str, ctype: str, name: str, value: str) -> str:
    pattern = rf"^(\s*static\s+constexpr\s+{re.escape(ctype)}\s+{re.escape(name)}\s*=\s*).+?;(?:\s*//.*)?$"
    replacement = rf"\g<1>{value};"
    out, count = re.subn(pattern, replacement, text, flags=re.M)
    if count != 1:
        raise PatchError(f"{name}: expected exactly one constant definition, found {count}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = ap.parse_args()
    tree = args.tree.resolve()
    path = tree / "src/wam/wam-params.h"
    if not path.exists():
        raise SystemExit(f"not the expected pinned base source tree: {tree}")

    text = path.read_text(encoding="utf-8")
    out = text
    out = replace_constant(out, "int64_t", "WAM_MAX_MONEY", "21'000'000 * WAM_COIN")
    out = replace_constant(out, "int64_t", "WAM_GENESIS_PREMINE", "0")
    out = replace_constant(out, "int64_t", "WAM_MINING_ALLOCATION", "WAM_MAX_MONEY")
    out = replace_constant(out, "int64_t", "WAM_INITIAL_BLOCK_SUBSIDY", "5 * WAM_COIN")
    out = replace_constant(out, "int", "WAM_SUBSIDY_HALVING_INTERVAL", "2'100'000")
    out = replace_constant(out, "int", "WAM_MAX_HALVINGS", "29")
    out = replace_constant(out, "int", "WAM_COINBASE_MATURITY", "100")

    path.write_text(out, encoding="utf-8")
    (tree / ".crakbit-monetary").write_text(
        "CRAK-003=applied\n"
        "max_money=21000000\n"
        "initial_subsidy=5\n"
        "halving_interval=2100000\n"
        "coinbase_maturity=100\n",
        encoding="utf-8",
    )
    print("CRAK-003 monetary patch: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        raise SystemExit(f"monetary patch failed: {exc}")
