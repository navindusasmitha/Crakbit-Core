#!/usr/bin/env python3
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PARAMS = (ROOT / "src/consensus/params.h").read_text()

COIN = 100_000_000
INITIAL = 10 * COIN
HALVING = 1_051_200
TREASURY_END = 400_000


def subsidy(height):
    if height == 0:
        return 0
    era = height // HALVING
    return 0 if era >= 64 else INITIAL >> era


class ConsensusPolicy(unittest.TestCase):
    def test_constants_locked(self):
        self.assertIn("1'051'200ULL", PARAMS)
        self.assertIn("TREASURY_PERCENT = 5", PARAMS)
        self.assertIn("BLOCK_TARGET_SECONDS = 120", PARAMS)
        self.assertIn("DGW_WINDOW = 24", PARAMS)
        self.assertIn("RANDOMX_EPOCH_BLOCKS = 256", PARAMS)
        self.assertIn("RANDOMX_SEED_LAG = 16", PARAMS)

    def test_zero_premine(self):
        self.assertEqual(subsidy(0), 0)

    def test_first_reward(self):
        self.assertEqual(subsidy(1), 10 * COIN)
        treasury = subsidy(1) * 5 // 100
        self.assertEqual(treasury, 50_000_000)
        self.assertEqual(subsidy(1) - treasury, 950_000_000)

    def test_halving_boundary(self):
        self.assertEqual(subsidy(HALVING - 1), 10 * COIN)
        self.assertEqual(subsidy(HALVING), 5 * COIN)

    def test_exact_scheduled_emission(self):
        total = 0
        era = 0
        while True:
            reward = INITIAL >> era
            if reward == 0:
                break
            total += reward * HALVING
            era += 1
        self.assertEqual(total, 2_102_399_986_334_400)

    def test_native_identity(self):
        self.assertIn("Crakbit Native Testnet v0.1", PARAMS)
        self.assertIn("2026-09-24", PARAMS)


if __name__ == "__main__":
    unittest.main()
