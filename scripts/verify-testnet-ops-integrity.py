#!/usr/bin/env python3
"""Fail-closed integrity checks for CRAK-026/027 public-testnet operations."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def require(path: str) -> Path:
    value = ROOT / path
    if not value.exists():
        errors.append(f"missing required path: {path}")
    return value


def require_text(path: str, needles: list[str]) -> None:
    value = require(path)
    if not value.is_file():
        return
    text = value.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            errors.append(f"{path} missing required reference: {needle}")


for path in (
    "network/TESTNET_BOOTSTRAP.json",
    "network/SOAK_POLICY.json",
    "scripts/crakbit-bootstrap.py",
    "scripts/crakbit-soak.py",
    "tests/bootstrap_unit.py",
    "tests/soak_unit.py",
    "docs/CRAK-026.md",
    "docs/CRAK-027.md",
    "docs/PUBLIC_TESTNET.md",
    "docs/TESTNET_SOAK.md",
    ".github/workflows/verify-testnet-bootstrap.yml",
    ".github/workflows/verify-testnet-soak.yml",
):
    require(path)

try:
    bootstrap = json.loads((ROOT / "network/TESTNET_BOOTSTRAP.json").read_text(encoding="utf-8"))
    security = bootstrap.get("security", {})
    if bootstrap.get("network") != "testnet4":
        errors.append("bootstrap network must remain testnet4")
    if security.get("rpc_public") is not False:
        errors.append("bootstrap RPC must remain non-public")
    if security.get("rpc_bind") not in {"127.0.0.1", "::1"}:
        errors.append("bootstrap RPC must remain loopback-bound")
    if security.get("p2p_public") is not True:
        errors.append("bootstrap P2P must remain public")
except (OSError, json.JSONDecodeError) as exc:
    errors.append(f"unable to parse TESTNET_BOOTSTRAP.json: {exc}")

try:
    policy = json.loads((ROOT / "network/SOAK_POLICY.json").read_text(encoding="utf-8"))
    if policy.get("network") != "testnet4":
        errors.append("soak policy network must remain testnet4")
    if float(policy.get("minimum_availability_ratio", 0)) < 0.99:
        errors.append("soak minimum availability must not fall below 0.99")
    if int(policy.get("minimum_nodes", 0)) < 2:
        errors.append("soak policy must require at least two nodes")
    if int(policy.get("minimum_failure_domains", 0)) < 2:
        errors.append("soak policy must require at least two failure domains")
    qualification = policy.get("qualification", {})
    if int(qualification.get("candidate", {}).get("minimum_window_seconds", 0)) < 86400:
        errors.append("candidate qualification must require at least 24 hours")
    launch = qualification.get("launch", {})
    if int(launch.get("minimum_window_seconds", 0)) < 259200:
        errors.append("launch qualification must require at least 72 hours")
    if launch.get("require_restart_recovery") is not True:
        errors.append("launch qualification must require restart recovery")
    if launch.get("require_reorg_observation") is not True:
        errors.append("launch qualification must require reorg evidence")
except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
    errors.append(f"unable to parse SOAK_POLICY.json: {exc}")

require_text(
    "scripts/crakbit-soak.py",
    [
        '"healthy": False',
        '"initialblockdownload"',
        '"verificationprogress"',
        '"connections"',
        "conflicting block hashes at the same final height",
        "no chain/mining progress observed during soak window",
        "launch qualification requires a recovered reorg observation",
        "bootstrap RPC must remain non-public",
    ],
)
require_text(
    "tests/soak_unit.py",
    [
        "test_launch_evidence_passes",
        "test_conflicting_equal_height_tip_fails",
        "test_launch_requires_full_window",
        "test_placeholder_bootstrap_is_rejected",
        "test_deep_reorg_is_rejected",
        "test_rpc_collector_uses_local_cli_contract",
    ],
)
for workflow in (
    ".github/workflows/verify-testnet-bootstrap.yml",
    ".github/workflows/verify-testnet-soak.yml",
):
    require_text(workflow, ["push:\n    branches:\n      - main", "pull_request:"])
require_text(
    ".github/workflows/verify-testnet-soak.yml",
    [
        "python3 tests/soak_unit.py",
        "validate --require-public-ready",
        "scripts/verify-repo-integrity.py",
        "scripts/verify-testnet-ops-integrity.py",
    ],
)

if errors:
    print("CRAK-026/027 testnet operations integrity: FAILED", file=sys.stderr)
    for item in errors:
        print(f" - {item}", file=sys.stderr)
    raise SystemExit(1)

print(
    "CRAK-026/027 testnet operations integrity: OK "
    "bootstrap_policy=locked rpc_public=false soak_24h=required soak_72h=required "
    "restart_recovery=required reorg_evidence=required"
)
