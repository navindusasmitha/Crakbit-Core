#!/usr/bin/env python3
from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "tests" / "genesis_vectors.json"


def compact_target(bits_hex: str) -> str:
    compact = int(bits_hex, 16)
    exponent = compact >> 24
    mantissa = compact & 0x007FFFFF
    target = mantissa << (8 * (exponent - 3)) if exponent > 3 else mantissa >> (8 * (3 - exponent))
    return f"{target:064x}"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: native_scanner_vector.py <crakminer-scan>")
    scanner = sys.argv[1]
    data = json.loads(VECTORS.read_text(encoding="utf-8"))["networks"]["regtest"]

    bits = int(data["bits"], 16)
    header = (
        struct.pack("<i", int(data["version"]))
        + (b"\x00" * 32)
        + bytes.fromhex(data["merkle_root"])[::-1]
        + struct.pack("<I", int(data["time"]))
        + struct.pack("<I", bits)
        + struct.pack("<I", 0)
    )
    assert len(header) == 80

    proc = subprocess.run(
        [
            scanner,
            "--header", header.hex(),
            "--target", compact_target(data["bits"][2:]),
            "--threads", "2",
            "--cpu-limit", "100",
            "--start-nonce", "0",
            "--max-hashes", str(int(data["nonce"]) + 1),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise SystemExit(f"scanner failed rc={proc.returncode}: {proc.stderr.strip()} {proc.stdout.strip()}")

    fields = dict(token.split("=", 1) for token in proc.stdout.strip().split() if "=" in token)
    nonce = int(fields.get("nonce", "-1"))
    block_hash = fields.get("hash")
    if nonce != int(data["nonce"]):
        raise SystemExit(f"expected nonce {data['nonce']}, got {nonce}")
    if block_hash != data["hash"]:
        raise SystemExit(f"expected hash {data['hash']}, got {block_hash}")

    print(f"CRAK-013 native scanner vector: OK nonce={nonce} hash={block_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
