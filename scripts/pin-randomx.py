#!/usr/bin/env python3
"""Override the pinned WAM reference's RandomX dependency for Crakbit testnet.

RandomX v1.2.2 fixed a rare ARM/RISC-V JIT hash correctness problem and
v1.2.3 is the current v1 maintenance release used by Crakbit Testnet v0.1.
This script is deliberately anchored: it aborts if the pinned WAM source no
longer contains the exact dependency line we reviewed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

OLD = 'RANDOMX_TAG="${RANDOMX_TAG:-v1.2.1}"'
NEW = 'RANDOMX_TAG="${RANDOMX_TAG:-v1.2.3}"'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    args = ap.parse_args()

    path = Path(args.tree).resolve() / 'scripts' / 'fetch-upstream.sh'
    text = path.read_text(encoding='utf-8')

    if NEW in text and OLD not in text:
        print(f'RandomX dependency already pinned to v1.2.3 in {path}')
        return 0

    count = text.count(OLD)
    if count != 1:
        raise SystemExit(
            f'expected exactly one reviewed RandomX v1.2.1 anchor in {path}, found {count}'
        )

    path.write_text(text.replace(OLD, NEW, 1), encoding='utf-8')
    print(f'Pinned RandomX v1.2.3 in {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
