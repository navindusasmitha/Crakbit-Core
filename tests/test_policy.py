#!/usr/bin/env python3
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADER = (ROOT / 'overlay/src/wam/wam-params.h').read_text(encoding='utf-8')
POOL = (ROOT / 'overlay/pool/lib/constants.js').read_text(encoding='utf-8')

COIN = 100_000_000
INITIAL = 10 * COIN
INTERVAL = 1_051_200
MAX_HALVINGS = 30
TREASURY_LAST = 400_000


def subsidy(height: int) -> int:
    if height <= 0:
        return 0
    halvings = (height - 1) // INTERVAL
    if halvings >= MAX_HALVINGS:
        return 0
    return INITIAL >> halvings


def treasury(height: int) -> int:
    if height < 1 or height > TREASURY_LAST:
        return 0
    return subsidy(height) * 5 // 100


class CrakbitPolicyTests(unittest.TestCase):
    def test_no_premine(self):
        self.assertIn('WAM_GENESIS_PREMINE = 0;', HEADER)
        self.assertEqual(subsidy(0), 0)

    def test_first_block(self):
        self.assertEqual(subsidy(1), 10 * COIN)
        self.assertEqual(treasury(1), int(0.5 * COIN))
        self.assertEqual(subsidy(1) - treasury(1), int(9.5 * COIN))

    def test_treasury_sunset(self):
        self.assertEqual(treasury(400_000), int(0.5 * COIN))
        self.assertEqual(treasury(400_001), 0)
        self.assertEqual(sum(treasury(h) for h in range(1, 400_001)), 200_000 * COIN)

    def test_halving_boundary(self):
        self.assertEqual(subsidy(INTERVAL), 10 * COIN)
        self.assertEqual(subsidy(INTERVAL + 1), 5 * COIN)

    def test_terminal_emission(self):
        total = 0
        for era in range(MAX_HALVINGS):
            total += INTERVAL * (INITIAL >> era)
        self.assertEqual(total, 2_102_399_986_334_400)
        self.assertEqual(total / COIN, 21_023_999.863344)
        self.assertEqual(INITIAL >> MAX_HALVINGS, 0)

    def test_header_constants_present(self):
        required = [
            "WAM_INITIAL_BLOCK_SUBSIDY = 10 * WAM_COIN",
            "WAM_SUBSIDY_HALVING_INTERVAL = 1'051'200",
            "WAM_DEVFEE_LAST_HEIGHT = 400'000",
            "WAM_POW_TARGET_SPACING = 120",
            '"Crakbit/RandomX/testnet-v0.1/2026"',
        ]
        for text in required:
            self.assertIn(text, HEADER)

    def test_pool_testnet_randomx_matches_chainparams_override(self):
        self.assertRegex(POOL, r'RANDOMX_EPOCH_BLOCKS:\s*256')
        self.assertRegex(POOL, r'RANDOMX_EPOCH_LAG:\s*16')
        self.assertIn("Crakbit/RandomX/testnet-v0.1/2026", POOL)


if __name__ == '__main__':
    unittest.main()
