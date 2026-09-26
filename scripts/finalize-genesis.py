#!/usr/bin/env python3
"""Freeze CRAK-006 genesis vectors into a materialized Crakbit Core tree."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARAMS = ROOT / "consensus" / "params.json"
TREE = ROOT / ".work" / "crakbit"
MANIFEST = ROOT / ".work" / "materialized-source.txt"
CHAINPARAMS = TREE / "src" / "kernel" / "chainparams.cpp"

DISCOVERY_MARKER = "        // CRAK-006 discovery pass: tests/genesis_probe.cpp mines/fixes the nonce."


def main() -> None:
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    networks = params["networks"]

    if not CHAINPARAMS.is_file():
        raise SystemExit("materialized chainparams.cpp missing; run scripts/materialize.py first")

    text = CHAINPARAMS.read_text(encoding="utf-8")
    if text.count(DISCOVERY_MARKER) != 2:
        raise SystemExit("expected exactly two CRAK-006 genesis discovery markers")

    for network_name in ("testnet4", "regtest"):
        genesis = networks[network_name]["genesis"]
        expected_hash = genesis.get("hash")
        expected_merkle = genesis.get("merkle_root")
        nonce = genesis.get("nonce")
        if not isinstance(nonce, int):
            raise SystemExit(f"{network_name}: genesis nonce is not frozen")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise SystemExit(f"{network_name}: genesis hash is not frozen")
        if not isinstance(expected_merkle, str) or len(expected_merkle) != 64:
            raise SystemExit(f"{network_name}: merkle root is not frozen")

        replacement = (
            f"        assert(consensus.hashGenesisBlock == uint256{{\"{expected_hash}\"}});\n"
            f"        assert(genesis.hashMerkleRoot == uint256{{\"{expected_merkle}\"}});"
        )
        text = text.replace(DISCOVERY_MARKER, replacement, 1)

    CHAINPARAMS.write_text(text, encoding="utf-8")

    manifest = MANIFEST.read_text(encoding="utf-8")
    manifest = manifest.replace(
        "stage=CRAK-006-network-genesis-discovery",
        "stage=CRAK-006-network-genesis-locked",
        1,
    )
    manifest += (
        f"testnet4_genesis={networks['testnet4']['genesis']['hash']}\n"
        f"regtest_genesis={networks['regtest']['genesis']['hash']}\n"
        "genesis_vectors_locked=true\n"
    )
    MANIFEST.write_text(manifest, encoding="utf-8")

    print("CRAK-006 genesis vectors locked into materialized source")


if __name__ == "__main__":
    main()
