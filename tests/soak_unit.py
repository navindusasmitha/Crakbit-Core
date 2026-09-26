#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("crakbit_soak", ROOT / "scripts" / "crakbit-soak.py")
assert SPEC and SPEC.loader
soak = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(soak)


POLICY = {
    "schema": 1,
    "network": "testnet4",
    "minimum_nodes": 2,
    "minimum_failure_domains": 2,
    "minimum_availability_ratio": 0.99,
    "maximum_consecutive_failures": 3,
    "maximum_tip_height_spread": 2,
    "maximum_header_lag": 2,
    "minimum_peer_connections": 1,
    "minimum_verification_progress": 0.999,
    "maximum_reorg_depth": 6,
    "qualification": {
        "smoke": {"minimum_window_seconds": 0, "require_restart_recovery": False, "require_reorg_observation": False},
        "candidate": {"minimum_window_seconds": 86400, "require_restart_recovery": True, "require_reorg_observation": False},
        "launch": {"minimum_window_seconds": 259200, "require_restart_recovery": True, "require_reorg_observation": True},
    },
}

BOOTSTRAP = {
    "schema": 1,
    "network": "testnet4",
    "minimum_public_nodes": 2,
    "minimum_failure_domains": 2,
    "nodes": [
        {"name": "seed-a", "endpoint": "seed-a.crakbit.example:48333", "region": "ap-south", "provider": "provider-a", "enabled": True},
        {"name": "seed-b", "endpoint": "seed-b.crakbit.example:48333", "region": "eu-west", "provider": "provider-b", "enabled": True},
    ],
    "security": {"rpc_bind": "127.0.0.1", "rpc_public": False, "p2p_public": True},
}


def observation(node: str, ts: int, height: int, block_hash: str, healthy: bool = True) -> dict:
    base = {
        "schema": 1,
        "kind": "observation",
        "network": "testnet4",
        "node": node,
        "timestamp_epoch": ts,
        "timestamp_utc": "fixture",
        "healthy": healthy,
    }
    if healthy:
        base.update(
            {
                "blocks": height,
                "headers": height,
                "bestblockhash": block_hash,
                "initialblockdownload": False,
                "verificationprogress": 1.0,
                "connections": 4,
                "connections_in": 2,
                "connections_out": 2,
                "uptime_seconds": 1000,
            }
        )
    else:
        base["error"] = "fixture failure"
    return base


def good_launch_evidence() -> tuple[list[dict], list[dict]]:
    start = 1_800_000_000
    step = 86_400
    observations: list[dict] = []
    for i, height in enumerate((100, 120, 140, 160)):
        ts = start + i * step
        block_hash = f"{height:064x}"
        observations.append(observation("seed-a", ts, height, block_hash))
        observations.append(observation("seed-b", ts, height, block_hash))
    events = [
        {"schema": 1, "kind": "event", "network": "testnet4", "node": "seed-a", "event": "restart", "timestamp_epoch": start + step + 10},
        {"schema": 1, "kind": "event", "network": "testnet4", "node": "seed-b", "event": "restart", "timestamp_epoch": start + step + 20},
        {"schema": 1, "kind": "event", "network": "testnet4", "node": "seed-a", "event": "reorg", "depth": 2, "timestamp_epoch": start + 2 * step + 10},
    ]
    return observations, events


class SoakEvaluationTests(unittest.TestCase):
    def test_launch_evidence_passes(self) -> None:
        observations, events = good_launch_evidence()
        result = soak.evaluate(deepcopy(BOOTSTRAP), deepcopy(POLICY), observations, events, "launch")
        self.assertTrue(result["healthy"], result["errors"])
        self.assertEqual(result["enabled_nodes"], 2)
        self.assertEqual(result["restart_recoveries"], 2)
        self.assertEqual(result["reorg_observations"], 1)
        self.assertGreater(result["progress_blocks"], 0)

    def test_conflicting_equal_height_tip_fails(self) -> None:
        observations, events = good_launch_evidence()
        observations[-1]["bestblockhash"] = "f" * 64
        result = soak.evaluate(deepcopy(BOOTSTRAP), deepcopy(POLICY), observations, events, "launch")
        self.assertFalse(result["healthy"])
        self.assertTrue(any("conflicting block hashes" in item for item in result["errors"]))

    def test_launch_requires_full_window(self) -> None:
        observations, events = good_launch_evidence()
        observations = [r for r in observations if r["timestamp_epoch"] < 1_800_000_000 + 259_200]
        result = soak.evaluate(deepcopy(BOOTSTRAP), deepcopy(POLICY), observations, events, "launch")
        self.assertFalse(result["healthy"])
        self.assertTrue(any("observation window" in item for item in result["errors"]))

    def test_placeholder_bootstrap_is_rejected(self) -> None:
        observations, events = good_launch_evidence()
        bootstrap = deepcopy(BOOTSTRAP)
        bootstrap["nodes"][0]["endpoint"] = "seed-a.example.invalid:48333"
        result = soak.evaluate(bootstrap, deepcopy(POLICY), observations, events, "launch")
        self.assertFalse(result["healthy"])
        self.assertTrue(any("not publicly routable" in item for item in result["errors"]))

    def test_deep_reorg_is_rejected(self) -> None:
        observations, events = good_launch_evidence()
        events[-1]["depth"] = 7
        result = soak.evaluate(deepcopy(BOOTSTRAP), deepcopy(POLICY), observations, events, "launch")
        self.assertFalse(result["healthy"])
        self.assertTrue(any("reorg depth" in item for item in result["errors"]))

    def test_rpc_collector_uses_local_cli_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "fake-cli"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "m=sys.argv[-1]\n"
                "if m=='getblockchaininfo': print(json.dumps({'blocks':42,'headers':42,'bestblockhash':'ab'*32,'initialblockdownload':False,'verificationprogress':1.0}))\n"
                "elif m=='getnetworkinfo': print(json.dumps({'connections':3,'connections_in':1,'connections_out':2}))\n"
                "elif m=='uptime': print('1234')\n"
                "else: raise SystemExit(2)\n",
                encoding="utf-8",
            )
            os.chmod(fake, 0o755)
            record = soak.collect_observation("seed-a", str(fake), None)
            self.assertTrue(record["healthy"])
            self.assertEqual(record["blocks"], 42)
            self.assertEqual(record["connections"], 3)
            self.assertEqual(record["uptime_seconds"], 1234)


if __name__ == "__main__":
    unittest.main(verbosity=2)
