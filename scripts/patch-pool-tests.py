#!/usr/bin/env python3
"""Rebase the pinned WAM pool accounting fixtures onto Crakbit policy."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected one match, found {n}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, label: str) -> str:
    out, n = re.subn(pattern, repl, text, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f"{label}: expected one match, found {n}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    args = ap.parse_args()
    root = Path(args.tree).resolve()
    p = root / 'pool/test/rewards.test.js'
    text = p.read_text(encoding='utf-8')

    text = once(text, 'const SUBSIDY = 50 * COIN;              // epoch 0',
                'const SUBSIDY = 10 * COIN;              // Crakbit epoch 0',
                'pool subsidy fixture')
    text = once(text, 'const DEVFEE = SUBSIDY * 0.05;          // 2.5 WAM, paid by consensus',
                'const DEVFEE = SUBSIDY * 0.05;          // 0.5 CBIT, paid by consensus',
                'pool treasury fixture comment')
    text = once(text, 'const DISTRIBUTABLE = SUBSIDY - DEVFEE; // 47.5 WAM',
                'const DISTRIBUTABLE = SUBSIDY - DEVFEE; // 9.5 CBIT',
                'pool distributable fixture comment')
    text = once(text, "test('treasury amount is exactly 2.5 WAM at epoch 0', () => {\n    assert.strictEqual(DEVFEE, 250000000);\n    assert.strictEqual(DISTRIBUTABLE, 4750000000);\n});",
                "test('treasury amount is exactly 0.5 CBIT at epoch 0', () => {\n    assert.strictEqual(DEVFEE, 50000000);\n    assert.strictEqual(DISTRIBUTABLE, 950000000);\n});",
                'epoch-zero pool values')

    text = once(text,
                ".update('WAM/RandomX/epoch-0/2026').digest('hex');",
                ".update('Crakbit/RandomX/testnet-v0.1/2026').digest('hex');",
                'pool RandomX bootstrap vector')
    text = once(text,
                "test('halving interval is 200,000', () => {\n    assert.strictEqual(C.SUBSIDY_HALVING_INTERVAL, 200000);\n});",
                "test('halving interval is 1,051,200', () => {\n    assert.strictEqual(C.SUBSIDY_HALVING_INTERVAL, 1051200);\n});",
                'pool halving constant test')
    text = once(text,
                "test('initial subsidy is 50 WAM', () => {\n    assert.strictEqual(C.INITIAL_BLOCK_SUBSIDY_WAM, 50);\n});",
                "test('initial subsidy is 10 CBIT', () => {\n    assert.strictEqual(C.INITIAL_BLOCK_SUBSIDY_WAM, 10);\n});",
                'pool initial subsidy constant test')
    text = once(text,
                "test('20,000,000 WAM is mined in total', () => {",
                "test('geometric subsidy ceiling is 21,024,000 CBIT before integer-rounding dust', () => {",
                'pool supply ceiling label')

    text = regex_once(
        text,
        r"test\('the sunset spans more than one halving epoch', \(\) => \{.*?\n\}\);",
        "test('the treasury sunset occurs before the first halving', () => {\n"
        "    assert.ok(C.DEVFEE_LAST_HEIGHT < C.SUBSIDY_HALVING_INTERVAL);\n"
        "});",
        'treasury epoch relation test')
    text = once(text,
                "test('lifetime treasury income is exactly 750,000 WAM', () => {",
                "test('lifetime treasury allocation is exactly 200,000 CBIT', () => {",
                'treasury lifetime label')
    text = once(text, '    assert.strictEqual(total, 750000 * COIN);',
                '    assert.strictEqual(total, 200000 * COIN);',
                'treasury lifetime value')

    text = regex_once(
        text,
        r"test\('founder \+ operating totals 12\.50% of the cap', \(\) => \{.*?\n\}\);",
        "test('Crakbit has zero genesis premine', () => {\n"
        "    assert.strictEqual(C.GENESIS_PREMINE_WAM, 0);\n"
        "});",
        'remove WAM founder-allocation fixture')
    text = regex_once(
        text,
        r"test\('public mining share is 87\.50%', \(\) => \{.*?\n\}\);",
        "test('treasury is carved from subsidy rather than added to the cap', () => {\n"
        "    const cap = C.MAX_MONEY_WAM * COIN;\n"
        "    const treasury = 200000 * COIN;\n"
        "    assert.ok(treasury < cap);\n"
        "    assert.strictEqual(C.GENESIS_PREMINE_WAM, 0);\n"
        "});",
        'replace WAM public-mining-share fixture')

    text = once(text, '    const subsidy = 12.5 * COIN;',
                '    const subsidy = 10 * COIN;',
                'post-sunset subsidy fixture')
    text = once(text,
                "poolAddress: 'wamrt1qwpz49ds2qwtkt7m0claxr03naqqjmx8c48qj39',",
                "poolAddress: 'cbtrt1qwpz49ds2qwtkt7m0claxr03naqqjmx8cg988s8',",
                'pool regtest address fixture')
    text = once(text, "coinbaseSignature: '/WAM-Pool/',",
                "coinbaseSignature: '/Crakbit-Pool/',",
                'pool coinbase signature fixture')
    text = text.replace('// SUBSIDY (50 WAM, epoch 0) is already defined above.',
                        '// SUBSIDY (10 CBIT, epoch 0) is already defined above.')
    text = text.replace(' WAM pool -- reward and serialization tests',
                        ' Crakbit pool -- reward and serialization tests')

    p.write_text(text, encoding='utf-8')
    print(f'patched Crakbit pool policy fixtures: {p}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
