#!/usr/bin/env python3
"""Run the materialized C++ ASERT probe against frozen JSON vectors."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "tests" / "asert_vectors.json").read_text(encoding="utf-8"))


def run(binary: str, *args: str) -> str:
    return subprocess.check_output([binary, *args], text=True).strip()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} <crakbit_asert_vector binary>")
    binary = sys.argv[1]
    profile = VECTORS["profile"]
    spacing = str(profile["target_spacing_seconds"])
    half_life = str(profile["half_life_seconds"])
    pow_limit_bits = profile["pow_limit_bits"]

    for vector in VECTORS["vectors"]:
        actual = run(
            binary,
            vector["ref_bits"],
            str(vector["time_diff"]),
            str(vector["height_diff"]),
            pow_limit_bits,
            spacing,
            half_life,
        )
        if actual != vector["expected_bits"]:
            raise SystemExit(
                f"{vector['name']}: C++ expected {vector['expected_bits']}, got {actual}"
            )

    smoke = run(binary, "--chain-smoke").splitlines()
    expected_smoke = [
        "first=1f0fffff",
        "fast_second=1f0ff437",
        "ideal_second=1f0fffff",
    ]
    if smoke != expected_smoke:
        raise SystemExit(f"ASERT chain smoke mismatch: expected {expected_smoke}, got {smoke}")

    print(f"CRAK-007 C++ ASERT vectors: OK ({len(VECTORS['vectors'])} cases + chain smoke)")


if __name__ == "__main__":
    main()
