#!/usr/bin/env python3
"""Patch the pinned reference miner's network address table for Crakbit."""
from __future__ import annotations

import argparse
from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    args = ap.parse_args()

    path = Path(args.tree).resolve() / 'miner/src/address.h'
    text = path.read_text(encoding='utf-8')
    text = once(text,
        'if (network == "testnet") return {"twam", 65, 128};',
        'if (network == "testnet") return {"tcb", 65, 128};',
        'testnet miner address table')
    text = once(text,
        'if (network == "regtest") return {"wamrt", 100, 196};',
        'if (network == "regtest") return {"cbtrt", 65, 128};',
        'regtest miner address table')
    text = once(text,
        'return {"wam", 73, 135};',
        'return {"cbit", 73, 135};',
        'mainnet miner address table')

    # User-facing diagnostics only; this does not affect consensus.
    text = text.replace('not a WAM one.', 'not a Crakbit one.')
    path.write_text(text, encoding='utf-8')
    print(f'patched Crakbit miner address table: {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
