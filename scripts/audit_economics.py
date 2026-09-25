#!/usr/bin/env python3
"""Fail unless CRAK-001/002 leave zero active premine and treasury economics."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / ".work" / "crakbit-source"


def require(text: str, pattern: str, label: str, *, minimum: int = 1) -> None:
    count = len(re.findall(pattern, text, flags=re.M | re.S))
    if count < minimum:
        raise SystemExit(f"AUDIT FAIL: {label}: expected >= {minimum}, found {count}")


def forbid(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, flags=re.M | re.S):
        raise SystemExit(f"AUDIT FAIL: forbidden active rule remains: {label}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = ap.parse_args()
    tree = args.tree.resolve()

    marker = tree / ".crakbit-economics"
    if not marker.exists():
        raise SystemExit("AUDIT FAIL: CRAK-001/002 marker missing")

    params = (tree / "src/wam/wam-params.h").read_text(encoding="utf-8")
    subsidy = (tree / "src/wam/consensus/subsidy.cpp").read_text(encoding="utf-8")
    devfee = (tree / "src/wam/consensus/devfee.cpp").read_text(encoding="utf-8")
    chainparams = (tree / "src/wam/chainparams.cpp").read_text(encoding="utf-8")

    require(params, r"WAM_GENESIS_PREMINE\s*=\s*0\s*;", "genesis premine constant is zero")
    require(params, r"WAM_DEVFEE_PERCENT\s*=\s*0\s*;", "dev-fee percent is zero")
    require(params, r"WAM_PREMINE_TRANCHE_AMOUNT\s*=\s*0\s*;", "premine tranche amount is zero")

    require(subsidy, r"if\s*\(nHeight\s*==\s*0\)\s*return\s+0\s*;", "height-zero subsidy has no premine")
    require(subsidy, r"bool\s+IsDevFeeActive\s*\([^)]*\)\s*\{\s*return\s+false\s*;\s*\}", "dev fee inactive")
    require(subsidy, r"CAmount\s+GetDevFeeAmount\s*\([^)]*\)\s*\{\s*return\s+0\s*;\s*\}", "dev fee amount zero")
    require(subsidy, r"CAmount\s+GetMinerSubsidy\s*\([^)]*\)\s*\{\s*return\s+nSubsidy\s*;\s*\}", "full subsidy goes to miner")
    require(subsidy, r"CAmount\s+GetLifetimeDevFee\s*\([^)]*\)\s*\{\s*return\s+0\s*;\s*\}", "lifetime dev fee zero")
    require(subsidy, r"CAmount\s+GetVestedPremine\s*\([^)]*\)\s*\{\s*return\s+0\s*;\s*\}", "vested premine zero")
    require(subsidy, r"CAmount\s+total\s*=\s*0\s*;", "supply baseline starts at zero")

    require(devfee, r"CAmount\s+GetPaidDevFee\s*\([^)]*\)\s*\{\s*return\s+0\s*;\s*\}", "paid dev fee zero")
    require(devfee, r"bool\s+CheckDevFeeOutput\s*\([^)]*\)\s*\{\s*return\s+true\s*;\s*\}", "dev-fee validation is inert")

    require(chainparams, r"consensus\.nGenesisPremine\s*=\s*0\s*;", "all chainparams premine fields zero", minimum=3)
    require(chainparams, r"consensus\.nDevFeePercent\s*=\s*0\s*;", "all chainparams dev-fee fields zero", minimum=3)
    require(chainparams, r"consensus\.nDevFeeStartHeight\s*=\s*0\s*;", "all dev-fee start heights zero", minimum=3)
    require(chainparams, r"consensus\.nDevFeeLastHeight\s*=\s*0\s*;", "all dev-fee end heights zero", minimum=3)
    require(chainparams, r"consensus\.devFeeAddress\.clear\(\)\s*;", "treasury addresses cleared", minimum=3)

    forbid(chainparams, r"consensus\.nGenesisPremine\s*=\s*WAM_GENESIS_PREMINE", "inherited premine assignment")
    forbid(chainparams, r"consensus\.nDevFeePercent\s*=\s*WAM_DEVFEE_PERCENT", "inherited dev-fee assignment")
    forbid(chainparams, r"consensus\.devFeeAddress\s*=\s*WAM_TREASURY_ADDRESS_", "active treasury address assignment")

    print("CRAK-001 audit: premine/founder economics = 0")
    print("CRAK-002 audit: treasury/dev-fee economics = 0")
    print("ECONOMICS AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
