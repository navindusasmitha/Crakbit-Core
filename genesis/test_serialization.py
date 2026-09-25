#!/usr/bin/env python3
"""Pure-Python serialization sanity check.

Reconstructs Bitcoin's real genesis transaction and 80-byte block header from
fields, then checks the known txid/merkle root and block hash. Crakbit uses the
same Bitcoin serialization and SHA256d block-ID layout, so this is a guardrail
before any custom genesis is generated.
"""

import hashlib
import struct

COIN = 100_000_000


def dsha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def compact_size(n: int) -> bytes:
    if n < 253:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


def main() -> int:
    timestamp = b"The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"
    script_sig = bytes.fromhex("04ffff001d010445") + timestamp
    pubkey = bytes.fromhex(
        "04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61de"
        "b649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f"
    )
    script_pubkey = b"\x41" + pubkey + b"\xac"

    tx = b"".join(
        [
            struct.pack("<I", 1),
            compact_size(1),
            bytes(32),
            struct.pack("<I", 0xFFFFFFFF),
            compact_size(len(script_sig)),
            script_sig,
            struct.pack("<I", 0xFFFFFFFF),
            compact_size(1),
            struct.pack("<Q", 50 * COIN),
            compact_size(len(script_pubkey)),
            script_pubkey,
            struct.pack("<I", 0),
        ]
    )

    tx_hash_internal = dsha256(tx)
    txid = tx_hash_internal[::-1].hex()
    expected_merkle = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
    assert txid == expected_merkle, f"genesis tx mismatch: {txid}"

    header = b"".join(
        [
            struct.pack("<I", 1),
            bytes(32),
            tx_hash_internal,
            struct.pack("<I", 1231006505),
            struct.pack("<I", 0x1D00FFFF),
            struct.pack("<I", 2083236893),
        ]
    )
    assert len(header) == 80

    block_id = dsha256(header)[::-1].hex()
    expected_block_id = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    assert block_id == expected_block_id, f"genesis block mismatch: {block_id}"

    print("Bitcoin serialization reference: PASS")
    print(f"merkle/txid: {txid}")
    print(f"block id:    {block_id}")
    print("header size: 80 bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
