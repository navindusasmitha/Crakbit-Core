#!/usr/bin/env python3
"""Apply the Crakbit testnet-v0.1 overlay to the pinned WAM source tree.

Every consensus-sensitive edit is anchored. If the pinned reference no longer
matches the expected source shape, this script aborts instead of guessing.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys

TESTNET_BURN = "T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb"
MAINNET_BURN = "WNg2svm2qApxheBKndKGQ9sRwporvRgRpT"
PHRASE = "Crakbit Testnet v0.1 - 22 Sep 2026 - Build verify decentralize"
BOOTSTRAP_KEY = "Crakbit/RandomX/testnet-v0.1/2026"
TESTNET_TIME = 1790035200


class PatchError(RuntimeError):
    pass


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: pathlib.Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_regex_once(text: str, pattern: str, repl: str, label: str, flags: int = 0) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one regex match, found {count}")
    return out


def class_slice(text: str, class_name: str, next_class: str | None) -> tuple[int, int, str]:
    start = text.find(f"class {class_name}")
    if start < 0:
        raise PatchError(f"missing {class_name}")
    if next_class:
        end = text.find(f"class {next_class}", start + 1)
        if end < 0:
            raise PatchError(f"missing class after {class_name}: {next_class}")
    else:
        end = len(text)
    return start, end, text[start:end]


def replace_class(text: str, class_name: str, next_class: str | None, transform) -> str:
    start, end, body = class_slice(text, class_name, next_class)
    changed = transform(body)
    if changed == body:
        raise PatchError(f"{class_name}: transform made no changes")
    return text[:start] + changed + text[end:]


def reset_min_chainwork(body: str, label: str) -> str:
    # The pinned WAM commit stores the hex string without a 0x prefix. Accept
    # either spelling so this anchor describes uint256S(hex), not typography.
    return replace_regex_once(
        body,
        r'consensus\.nMinimumChainWork = uint256S\("(?:0x)?[0-9a-fA-F]+"\);',
        'consensus.nMinimumChainWork = uint256{};',
        label,
    )


def patch_chainparams(path: pathlib.Path) -> None:
    src = read(path)

    src = replace_regex_once(
        src, r'static const std::string WAM_FOUNDER_ADDRESS_MAINNET = "[^"]+";',
        f'static const std::string WAM_FOUNDER_ADDRESS_MAINNET = "{MAINNET_BURN}";',
        "mainnet founder compatibility address")
    src = replace_regex_once(
        src, r'static const std::string WAM_FOUNDER_ADDRESS_TESTNET = "[^"]+";',
        f'static const std::string WAM_FOUNDER_ADDRESS_TESTNET = "{TESTNET_BURN}";',
        "testnet founder compatibility address")
    src = replace_regex_once(
        src, r'static const std::string WAM_TREASURY_ADDRESS_MAINNET = "[^"]+";',
        f'static const std::string WAM_TREASURY_ADDRESS_MAINNET = "{MAINNET_BURN}";',
        "mainnet treasury placeholder")
    src = replace_regex_once(
        src, r'static const std::string WAM_TREASURY_ADDRESS_TESTNET = "[^"]+";',
        f'static const std::string WAM_TREASURY_ADDRESS_TESTNET = "{TESTNET_BURN}";',
        "testnet treasury burn address")

    def mainnet(body: str) -> str:
        # CMainParams is still constructed by Core while parsing options on a
        # testnet run. Keep it structurally valid but undiscoverable; a future
        # mainnet code-freeze commit must replace this placeholder genesis.
        body = replace_once(
            body,
            'consensus.powLimit = uint256S("00000fffff000000000000000000000000000000000000000000000000000000");',
            'consensus.powLimit = uint256S("0000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");',
            "placeholder mainnet powLimit")
        body = replace_once(body, '/*nBits=*/   0x1e0ffff0,', '/*nBits=*/   0x1f00ffff,',
                            "placeholder mainnet genesis bits")
        body = reset_min_chainwork(body, "mainnet minimum chainwork reset")
        body = replace_regex_once(
            body,
            r'pchMessageStart\[0\] = 0x57;[^\n]*\n\s*pchMessageStart\[1\] = 0x41;[^\n]*\n\s*pchMessageStart\[2\] = 0x4d;[^\n]*\n\s*pchMessageStart\[3\] = 0x21;[^\n]*',
            'pchMessageStart[0] = 0x43; // C\n        pchMessageStart[1] = 0x42; // B\n        pchMessageStart[2] = 0x49; // I\n        pchMessageStart[3] = 0x54; // T',
            "mainnet message magic")
        body = replace_once(body, 'bech32_hrp = "wam";', 'bech32_hrp = "cbit";', "mainnet bech32")
        body = re.sub(r'\s*vSeeds\.emplace_back\("seed[123]\.wamcoin\.org\."\);', '', body)
        body = re.sub(
            r'\s*vFixedSeeds = std::vector<uint8_t>\(std::begin\(chainparams_seed_main\),\s*\n\s*std::end\(chainparams_seed_main\)\);',
            '\n        vFixedSeeds.clear();', body, count=1)
        return body

    src = replace_class(src, "CMainParams", "CTestNetParams", mainnet)

    def testnet(body: str) -> str:
        body = replace_once(
            body,
            'consensus.powLimit = uint256S("00000fffff000000000000000000000000000000000000000000000000000000");',
            'consensus.powLimit = uint256S("0000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");',
            "testnet powLimit")
        body = reset_min_chainwork(body, "testnet minimum chainwork reset")
        body = replace_regex_once(
            body,
            r'pchMessageStart\[0\] = 0x77;[^\n]*\n\s*pchMessageStart\[1\] = 0x61;[^\n]*\n\s*pchMessageStart\[2\] = 0x6d;[^\n]*\n\s*pchMessageStart\[3\] = 0x21;[^\n]*',
            'pchMessageStart[0] = 0x63; // c\n        pchMessageStart[1] = 0x62; // b\n        pchMessageStart[2] = 0x69; // i\n        pchMessageStart[3] = 0x74; // t',
            "testnet message magic")
        body = replace_once(body, '/*nBits=*/   0x1e0ffff0,', '/*nBits=*/   0x1f00ffff,',
                            "testnet genesis bits")
        body = replace_once(body, 'bech32_hrp = "twam";', 'bech32_hrp = "tcb";', "testnet bech32")
        body = re.sub(
            r'\s*vFixedSeeds = std::vector<uint8_t>\(std::begin\(chainparams_seed_test\),\s*\n\s*std::end\(chainparams_seed_test\)\);',
            '\n        vFixedSeeds.clear();', body, count=1)
        body = re.sub(r'\s*vSeeds\.emplace_back\("testnet-seed\.wamcoin\.org\."\);', '', body, count=1)
        return body

    src = replace_class(src, "CTestNetParams", "CRegTestParams", testnet)

    def regtest(body: str) -> str:
        body = replace_once(body, 'bech32_hrp = "wamrt";', 'bech32_hrp = "cbtrt";', "regtest bech32")
        body = replace_regex_once(
            body,
            r'pchMessageStart\[0\] = 0x57;\s*\n\s*pchMessageStart\[1\] = 0x41;\s*\n\s*pchMessageStart\[2\] = 0x4d;\s*\n\s*pchMessageStart\[3\] = 0x52;[^\n]*',
            'pchMessageStart[0] = 0xfa;\n        pchMessageStart[1] = 0xc3;\n        pchMessageStart[2] = 0xb6;\n        pchMessageStart[3] = 0xda;',
            "regtest message magic")
        return body

    src = replace_class(src, "CRegTestParams", None, regtest)
    write(path, src)


def patch_genesis_generator(path: pathlib.Path) -> None:
    src = read(path)
    src = replace_once(src, 'GENESIS_PREMINE = 2_000_000 * COIN', 'GENESIS_PREMINE = 0', "genesis premine")
    src = replace_regex_once(src, r'GENESIS_PHRASE = "[^"]+"', f'GENESIS_PHRASE = "{PHRASE}"', "genesis phrase")
    src = replace_regex_once(src, r'RANDOMX_BOOTSTRAP_KEY = b"[^"]+"', f'RANDOMX_BOOTSTRAP_KEY = b"{BOOTSTRAP_KEY}"', "RandomX bootstrap key")
    src = replace_regex_once(src, r'GENESIS_TIME = \d+', f'GENESIS_TIME = {TESTNET_TIME}', "placeholder mainnet genesis time")
    src = replace_regex_once(src, r'TESTNET_GENESIS_TIME = \d+', f'TESTNET_GENESIS_TIME = {TESTNET_TIME}', "testnet genesis time")
    src = replace_once(src, 'PREMINE_TRANCHES = 5', 'PREMINE_TRANCHES = 1', "zero-premine tranche count")
    src = replace_once(src, 'PREMINE_TRANCHE_AMOUNT = 400_000 * COIN', 'PREMINE_TRANCHE_AMOUNT = 0', "zero-premine tranche amount")
    src = replace_regex_once(src, r'PREMINE_UNLOCK_TIMES = \[.*?\]\n', 'PREMINE_UNLOCK_TIMES = [0]\n',
                             "zero-premine unlock table", flags=re.S)
    old_lock_assert = '''assert all(t > 500_000_000 for t in PREMINE_UNLOCK_TIMES), \\
    "every tranche must carry a real time lock -- a value below the CLTV " \\
    "threshold would be read as a block height and unlock almost at once"\n'''
    src = replace_once(src, old_lock_assert, 'assert GENESIS_PREMINE == 0\n', "zero-premine lock assertion")
    src = replace_once(
        src,
        '"mainnet": dict(time=GENESIS_TIME,         bits=0x1E0FFFF0, pubkey=73, script=135, first="W"),',
        '"mainnet": dict(time=GENESIS_TIME,         bits=0x1F00FFFF, pubkey=73, script=135, first="W"),',
        "placeholder mainnet genesis target")
    src = replace_once(
        src,
        '"testnet": dict(time=TESTNET_GENESIS_TIME, bits=0x1E0FFFF0, pubkey=65, script=128, first="T"),',
        '"testnet": dict(time=TESTNET_GENESIS_TIME, bits=0x1F00FFFF, pubkey=65, script=128, first="T"),',
        "testnet genesis target")
    src = src.replace('Mine the WAM Coin genesis block.', 'Mine the Crakbit testnet genesis block.')
    src = src.replace(' WAM Coin genesis generator -- ', ' Crakbit genesis generator -- ')
    write(path, src)


def patch_pool_config(path: pathlib.Path) -> None:
    src = read(path)
    src = src.replace('"coinbaseSignature": "/WAM-Pool/"', '"coinbaseSignature": "/Crakbit-Pool/"')
    src = src.replace('"poolAddress": "twam1q3rzkye9fxxyelxq3thca59f5245cer69pq5mkm"',
                      f'"poolAddress": "{TESTNET_BURN}"')
    src = src.replace('"redisPrefix": "wamtn"', '"redisPrefix": "cbittn"')
    src = src.replace('"port": 19554', '"port": 29110')
    write(path, src)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True, help='checked-out pinned WAM source tree')
    ap.add_argument('--overlay', required=True, help='Crakbit overlay directory')
    args = ap.parse_args()

    tree = pathlib.Path(args.tree).resolve()
    overlay = pathlib.Path(args.overlay).resolve()
    if not (tree / 'src/wam/chainparams.cpp').exists():
        raise PatchError(f'{tree} is not the expected WAM reference tree')

    shutil.copy2(overlay / 'src/wam/wam-params.h', tree / 'src/wam/wam-params.h')
    shutil.copy2(overlay / 'pool/lib/constants.js', tree / 'pool/lib/constants.js')
    patch_chainparams(tree / 'src/wam/chainparams.cpp')
    patch_genesis_generator(tree / 'genesis/genesis_generator.py')
    patch_pool_config(tree / 'pool/config.testnet.json')

    (tree / '.crakbit-overlay').write_text(
        'network=testnet-v0.1\n'
        f'genesis_phrase={PHRASE}\n'
        f'randomx_bootstrap_key={BOOTSTRAP_KEY}\n',
        encoding='utf-8')
    print(f'Crakbit overlay applied to {tree}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f'error: {exc}', file=sys.stderr)
        raise SystemExit(2)
