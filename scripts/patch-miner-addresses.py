#!/usr/bin/env python3
"""Patch the pinned reference miner's network address table/tests for Crakbit."""
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
    root = Path(args.tree).resolve()

    path = root / 'miner/src/address.h'
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
    text = text.replace('not a WAM one.', 'not a Crakbit one.')
    path.write_text(text, encoding='utf-8')

    # Recompute the reference bech32 vectors for the new HRPs while preserving
    # the exact witness programs/scripts that the original tests verify.
    test = root / 'miner/test/address_test.cpp'
    t = test.read_text(encoding='utf-8')
    replacements = [
        ('wam1qrulaxxlqf65madsmhqrevf467r6qmgdrxhf9yw',
         'cbit1qrulaxxlqf65madsmhqrevf467r6qmgdr8nu2u4'),
        ('wam1q5lsgy00xkq2axdy6w985htrlxlpxcaw9kgnm8c',
         'cbit1q5lsgy00xkq2axdy6w985htrlxlpxcaw9hvx5lr'),
        ('wam1qrulaxxlqf65madsmhqrevf467r6qmgdrxhf9yx',
         'cbit1qrulaxxlqf65madsmhqrevf467r6qmgdr8nu2ux'),
        ('twam1qrulaxxlqf65madsmhqrevf467r6qmgdrxhnxymw',
         'tcb1qrulaxxlqf65madsmhqrevf467r6qmgdr2xlwy0'),
        ('Refuses("wam1", "a prefix with no payload");',
         'Refuses("cbit1", "a prefix with no payload");'),
    ]
    for i, (old, new) in enumerate(replacements, 1):
        t = once(t, old, new, f'miner address test vector {i}')
    t = t.replace('a WAM testnet address given to a mainnet miner',
                  'a Crakbit testnet address given to a mainnet miner')
    test.write_text(t, encoding='utf-8')

    solo = root / 'miner/test/solo_template_test.cpp'
    s = solo.read_text(encoding='utf-8')
    s = once(s,
        'wamrt1q9uynnmupf5jl920vgztyef0v3esfjvdzfxfhyt',
        'cbtrt1q9uynnmupf5jl920vgztyef0v3esfjvdz5ywz9f',
        'regtest solo-miner bech32 vector')
    s = s.replace('/wam-miner/', '/crakbit-miner/')
    solo.write_text(s, encoding='utf-8')

    print(f'patched Crakbit miner address table/tests under {root / "miner"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
