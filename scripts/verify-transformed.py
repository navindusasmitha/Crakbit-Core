#!/usr/bin/env python3
"""Fail-fast verifier for a transformed Crakbit testnet source tree."""
from __future__ import annotations

import argparse
from pathlib import Path


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f'missing {label}: {needle!r}')


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SystemExit(f'forbidden {label} survived transform: {needle!r}')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    args = ap.parse_args()
    root = Path(args.tree).resolve()

    chain = (root / 'src/wam/chainparams.cpp').read_text(encoding='utf-8')
    params = (root / 'src/wam/wam-params.h').read_text(encoding='utf-8')
    genesis = (root / 'genesis/genesis_generator.py').read_text(encoding='utf-8')
    fetch = (root / 'scripts/fetch-upstream.sh').read_text(encoding='utf-8')
    pool = (root / 'pool/config.testnet.json').read_text(encoding='utf-8')

    # Network identity.
    require(chain, 'bech32_hrp = "tcb";', 'Crakbit testnet bech32 HRP')
    require(chain, 'pchMessageStart[0] = 0x63;', 'testnet message magic byte 0')
    require(chain, 'pchMessageStart[1] = 0x62;', 'testnet message magic byte 1')
    require(chain, 'pchMessageStart[2] = 0x69;', 'testnet message magic byte 2')
    require(chain, 'pchMessageStart[3] = 0x74;', 'testnet message magic byte 3')
    forbid(chain, 'testnet-seed.wamcoin.org', 'WAM testnet DNS seed')
    forbid(chain, 'seed1.wamcoin.org', 'WAM mainnet DNS seed 1')
    forbid(chain, 'seed2.wamcoin.org', 'WAM mainnet DNS seed 2')
    forbid(chain, 'seed3.wamcoin.org', 'WAM mainnet DNS seed 3')

    # Consensus/economics.
    for needle, label in [
        ("WAM_GENESIS_PREMINE = 0;", 'zero premine'),
        ("WAM_INITIAL_BLOCK_SUBSIDY = 10 * WAM_COIN", '10 CBIT subsidy'),
        ("WAM_SUBSIDY_HALVING_INTERVAL = 1'051'200", 'halving interval'),
        ("WAM_DEVFEE_PERCENT = 5", 'treasury percentage'),
        ("WAM_DEVFEE_LAST_HEIGHT = 400'000", 'treasury sunset'),
        ("WAM_POW_TARGET_SPACING = 120", '120 second spacing'),
        ("WAM_TESTNET_P2P_PORT = 29111", 'testnet P2P port'),
        ("WAM_TESTNET_RPC_PORT = 29110", 'testnet RPC port'),
    ]:
        require(params, needle, label)

    # Genesis/PoW domain separation.
    require(genesis, 'Crakbit Testnet v0.1 - 22 Sep 2026 - Build verify decentralize',
            'Crakbit genesis phrase')
    require(genesis, 'Crakbit/RandomX/testnet-v0.1/2026', 'Crakbit RandomX bootstrap key')
    require(fetch, 'RANDOMX_TAG="${RANDOMX_TAG:-v1.2.3}"', 'RandomX v1.2.3 pin')

    # Pool must talk to Crakbit testnet RPC, not the reference network.
    require(pool, '"port": 29110', 'pool daemon RPC port')
    require(pool, '"redisPrefix": "cbittn"', 'pool Redis namespace')
    require(pool, '"coinbaseSignature": "/Crakbit-Pool/"', 'pool coinbase signature')

    print('Crakbit transformed-source invariants: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
