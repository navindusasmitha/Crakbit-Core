#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pool = load("crakpool_unit", ROOT / "scripts" / "crakpool.py")
worker = load("crakminer_stratum_unit", ROOT / "scripts" / "crakminer-stratum.py")


def h256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def full_merkle(leaves: list[bytes]) -> bytes:
    level = leaves[:]
    while len(level) > 1:
        if len(level) & 1:
            level.append(level[-1])
        level = [h256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def main() -> None:
    assert pool.bip34_height_prefix(0) == bytes.fromhex("00")
    assert pool.bip34_height_prefix(1) == bytes.fromhex("51")
    assert pool.bip34_height_prefix(16) == bytes.fromhex("60")
    assert pool.bip34_height_prefix(17) == bytes.fromhex("0111")
    assert pool.bip34_height_prefix(128) == bytes.fromhex("028000")

    for diff in ("1", "0.0001", "0.000000001"):
        assert pool.difficulty_target(diff) == worker.difficulty_target(diff)

    # Regtest's 0x207fffff compact target is much easier than diff1 and must
    # decode identically on the worker side.
    reg_target = worker.compact_target(0x207FFFFF)
    assert reg_target == int("7fffff" + "00" * 29, 16)
    assert worker.difficulty_target("0.000000001") < reg_target

    coinbase = h256(b"synthetic coinbase")
    txids = [h256(b"tx-a"), h256(b"tx-b"), h256(b"tx-c")]
    template = {"transactions": [{"txid": txid[::-1].hex()} for txid in txids]}
    branch = pool.merkle_branch_for_coinbase(template)
    reconstructed = pool.merkle_from_coinbase(coinbase, branch)
    assert reconstructed == full_merkle([coinbase, *txids])

    # Exercise the odd-leaf duplication path separately.
    template2 = {"transactions": [{"txid": txid[::-1].hex()} for txid in txids[:2]]}
    branch2 = pool.merkle_branch_for_coinbase(template2)
    reconstructed2 = pool.merkle_from_coinbase(coinbase, branch2)
    assert reconstructed2 == full_merkle([coinbase, *txids[:2]])

    print("CRAK-014 Stratum protocol unit vectors: OK")


if __name__ == "__main__":
    main()
