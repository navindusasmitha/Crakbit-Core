#!/usr/bin/env python3
"""Dependency-free sanity check for the reserved Crakbit Base58 prefixes."""
import hashlib
import json
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parents[1]
PARAMS = json.loads((ROOT / 'consensus' / 'params.json').read_text())
NET = PARAMS['network_separation']['testnet']
ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, 'big')
    out = ''
    while n:
        n, r = divmod(n, 58)
        out = ALPHABET[r] + out
    zeroes = len(data) - len(data.lstrip(b'\0'))
    return '1' * zeroes + (out or '')


def base58check(version: int, payload: bytes) -> str:
    raw = bytes([version]) + payload
    checksum = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[:4]
    return b58encode(raw + checksum)


def check_prefix(version: int, expected: str) -> None:
    payloads = [bytes(20), bytes([255]) * 20]
    rng = random.Random(0x4352414B)
    payloads += [rng.randbytes(20) for _ in range(5000)]
    bad = [base58check(version, p) for p in payloads if not base58check(version, p).startswith(expected)]
    if bad:
        raise SystemExit(f'prefix {version} is not stable {expected!r}: example {bad[0]}')


check_prefix(NET['pubkey_address_version'], 'C')
check_prefix(NET['script_address_version'], 'c')
print('Crakbit Base58 prefix checks: OK')
