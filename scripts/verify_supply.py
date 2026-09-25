#!/usr/bin/env python3
"""Independent Crakbit monetary-supply verifier.

Reads consensus/params.json, reproduces the integer halving schedule in base
units, and fails if any premine/treasury rule is non-zero or if terminal
issuance exceeds the declared ceiling.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARAMS = ROOT / "consensus" / "params.json"
COIN = 100_000_000


def load_params() -> dict:
    return json.loads(PARAMS.read_text(encoding="utf-8"))


def schedule(params: dict):
    money = params["money"]
    subsidy = int(money["initial_subsidy_coins"] * COIN)
    interval = int(money["halving_interval_blocks"])
    height = 0
    epoch = 0
    total = 0
    while subsidy > 0:
        epoch_total = subsidy * interval
        total += epoch_total
        yield {
            "epoch": epoch,
            "start_height": height,
            "end_height": height + interval - 1,
            "subsidy": subsidy,
            "epoch_total": epoch_total,
            "cumulative": total,
        }
        subsidy //= 2
        height += interval
        epoch += 1


def coins(v: int) -> str:
    whole, frac = divmod(v, COIN)
    return f"{whole}.{frac:08d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schedule", action="store_true", help="print every emission epoch")
    args = ap.parse_args()

    params = load_params()
    money = params["money"]

    assert money["decimals"] == 8, "Crakbit consensus currently requires 8 decimals"
    assert money["premine_coins"] == 0, "premine must remain zero"
    assert money["treasury_percent"] == 0, "treasury/dev fee must remain zero"

    rows = list(schedule(params))
    terminal = rows[-1]["cumulative"] if rows else 0
    ceiling = int(money["intended_max_supply_coins"] * COIN)

    assert terminal <= ceiling, (
        f"terminal issuance {coins(terminal)} exceeds ceiling {coins(ceiling)}"
    )

    # Exact value for the v0.1 monetary constants. This catches accidental
    # changes that still happen to stay below 21M.
    expected_terminal = 2_099_999_972_700_000
    assert terminal == expected_terminal, (
        f"unexpected v0.1 terminal issuance: {terminal} != {expected_terminal}"
    )

    if args.schedule:
        print("epoch  heights                         subsidy        epoch total      cumulative")
        for r in rows:
            print(
                f"{r['epoch']:>5}  {r['start_height']:>9}-{r['end_height']:<9}  "
                f"{coins(r['subsidy']):>13}  {coins(r['epoch_total']):>15}  "
                f"{coins(r['cumulative']):>15}"
            )

    print(f"terminal issuance: {coins(terminal)} CRAK")
    print(f"declared ceiling:  {coins(ceiling)} CRAK")
    print("premine:           0 CRAK")
    print("treasury/dev fee:  0%")
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
