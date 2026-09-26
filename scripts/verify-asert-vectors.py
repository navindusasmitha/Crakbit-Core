#!/usr/bin/env python3
"""Independent unlimited-integer verifier for CRAK-007 ASERT vectors."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARAMS = json.loads((ROOT / "consensus" / "params.json").read_text(encoding="utf-8"))
VECTORS = json.loads((ROOT / "tests" / "asert_vectors.json").read_text(encoding="utf-8"))


def bits_to_target(nbits: int) -> int:
    size = nbits >> 24
    word = nbits & 0x007FFFFF
    if size <= 3:
        return word >> (8 * (3 - size))
    return word << (8 * (size - 3))


def target_to_bits(value: int) -> int:
    if value == 0:
        return 0
    size = (value.bit_length() + 7) // 8
    if size <= 3:
        compact = value << (8 * (3 - size))
    else:
        compact = value >> (8 * (size - 3))
    if compact & 0x00800000:
        compact >>= 8
        size += 1
    compact &= 0x007FFFFF
    compact |= size << 24
    return compact


def trunc_div(numerator: int, denominator: int) -> int:
    if numerator >= 0:
        return numerator // denominator
    return -((-numerator) // denominator)


def calculate_asert(ref_target: int, spacing: int, time_diff: int,
                    height_diff: int, pow_limit: int, half_life: int) -> int:
    drift = time_diff - spacing * (height_diff + 1)
    exponent = trunc_div(drift * 65536, half_life)
    shifts = exponent >> 16
    frac = exponent - shifts * 65536
    assert 0 <= frac < 65536

    factor = 65536 + ((
        195766423245049 * frac
        + 971821376 * frac * frac
        + 5127 * frac * frac * frac
        + (1 << 47)
    ) >> 48)

    value = ref_target * factor
    shifts -= 16
    if shifts <= 0:
        value >>= -shifts
    else:
        value <<= shifts

    if value == 0:
        value = 1
    return min(value, pow_limit)


def main() -> None:
    profile = VECTORS["profile"]
    difficulty = PARAMS["difficulty"]
    pow_params = PARAMS["proof_of_work"]

    if profile["target_spacing_seconds"] != pow_params["target_spacing_seconds"]:
        raise SystemExit("ASERT vector spacing differs from consensus params")
    if profile["half_life_seconds"] != difficulty["half_life_seconds"]:
        raise SystemExit("ASERT vector half-life differs from consensus params")
    if profile["anchor_mode"] != "genesis_conceptual_parent_minus_one_spacing":
        raise SystemExit("unexpected ASERT anchor mode")

    testnet_bits = PARAMS["networks"]["testnet4"]["genesis"]["bits"].removeprefix("0x")
    if profile["pow_limit_bits"] != testnet_bits:
        raise SystemExit("ASERT pow-limit compact value must match testnet genesis target")

    spacing = int(profile["target_spacing_seconds"])
    half_life = int(profile["half_life_seconds"])
    pow_limit = bits_to_target(int(profile["pow_limit_bits"], 16))

    for vector in VECTORS["vectors"]:
        ref_target = bits_to_target(int(vector["ref_bits"], 16))
        if ref_target <= 0 or ref_target > pow_limit:
            raise SystemExit(f"{vector['name']}: invalid reference target")
        actual_target = calculate_asert(
            ref_target,
            spacing,
            int(vector["time_diff"]),
            int(vector["height_diff"]),
            pow_limit,
            half_life,
        )
        actual_bits = f"{target_to_bits(actual_target):08x}"
        if actual_bits != vector["expected_bits"]:
            raise SystemExit(
                f"{vector['name']}: expected {vector['expected_bits']}, got {actual_bits}"
            )

    print(f"CRAK-007 ASERT vectors: OK ({len(VECTORS['vectors'])} cases)")


if __name__ == "__main__":
    main()
