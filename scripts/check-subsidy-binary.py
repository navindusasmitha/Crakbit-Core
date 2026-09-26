#!/usr/bin/env python3
"""Check the compiled CRAK-008 subsidy probe against frozen vectors."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "tests" / "subsidy_vectors.json").read_text(encoding="utf-8"))


def run(binary: str, *args: str) -> str:
    return subprocess.check_output([binary, *args], text=True).strip()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check-subsidy-binary.py <crakbit_subsidy_vector>")
    binary = sys.argv[1]
    profile = VECTORS["profile"]

    maturity = int(run(binary, "--maturity"))
    if maturity != profile["coinbase_maturity_blocks"]:
        raise SystemExit(f"coinbase maturity mismatch: {maturity}")

    total = int(run(binary, "--supply"))
    if total != profile["integer_rounded_max_subsidy_sats"]:
        raise SystemExit(f"integer-rounded supply mismatch: {total}")

    for vector in VECTORS["vectors"]:
        actual = int(run(binary, "--height", str(vector["height"])))
        if actual != vector["expected_sats"]:
            raise SystemExit(
                f"{vector['name']}: height {vector['height']} expected "
                f"{vector['expected_sats']} sats, got {actual}"
            )

    print(
        "CRAK-008 compiled subsidy vectors: OK "
        f"({len(VECTORS['vectors'])} heights, maturity={maturity}, total={total} sats)"
    )


if __name__ == "__main__":
    main()
