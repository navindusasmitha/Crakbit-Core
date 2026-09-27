#!/usr/bin/env python3
"""Fail-closed CRAK-029 miner/node interoperability and release-rehearsal gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def require(path: str) -> Path:
    p = ROOT / path
    if not p.is_file():
        fail(f"missing required CRAK-029 file: {path}")
    return p


def require_text(path: str, needles: list[str]) -> None:
    p = require(path)
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            fail(f"{path} missing required CRAK-029 contract: {needle}")


matrix_path = require("release/INTEROP_MATRIX.json")
require("tests/interop_protocol_probe.py")
require("tests/release_rehearsal_smoke.sh")
require("docs/CRAK-029.md")
require(".github/workflows/verify-interoperability.yml")

try:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"unable to parse release/INTEROP_MATRIX.json: {exc}")
    matrix = {}

if matrix.get("schema") != 1:
    fail("interop matrix schema must remain 1")
if matrix.get("milestone") != "CRAK-029":
    fail("interop matrix milestone must remain CRAK-029")
if matrix.get("channel") != "testnet":
    fail("CRAK-029 rehearsal channel must remain testnet")

arches = matrix.get("native_architectures", {})
expected_runners = {"x86_64": "ubuntu-24.04", "arm64": "ubuntu-24.04-arm"}
for arch, runner in expected_runners.items():
    entry = arches.get(arch, {})
    if entry.get("required") is not True:
        fail(f"native architecture must remain required: {arch}")
    if entry.get("runner") != runner:
        fail(f"native runner drift for {arch}: expected {runner}")

required_commands = set(matrix.get("required_commands", []))
for command in {
    "crakbitd", "crakbit-cli", "crakbit-start", "crakbit-mine",
    "crakminer-scan", "crakminer-native", "crakminer-stratum",
    "crakpool", "crakpool-stats", "crakpool-edge",
}:
    if command not in required_commands:
        fail(f"interop required command missing: {command}")

protocols = matrix.get("protocols", {})
gbt = protocols.get("getblocktemplate", {})
if gbt.get("reference_client") != "crakminer-native" or gbt.get("must_mine_block") is not True:
    fail("getblocktemplate must be mined by crakminer-native")
stratum = protocols.get("stratum_v1", {})
if stratum.get("server") != "crakpool":
    fail("Stratum server must remain crakpool")
if stratum.get("reference_client") != "crakminer-stratum":
    fail("Stratum reference client must remain crakminer-stratum")
if stratum.get("independent_json_client_required") is not True:
    fail("independent Stratum JSON client must remain required")
if stratum.get("reference_client_must_submit_share") is not True:
    fail("reference Stratum client must submit an accepted share")
methods = set(stratum.get("required_methods", []))
for method in {"mining.subscribe", "mining.authorize", "mining.set_difficulty", "mining.notify", "mining.submit"}:
    if method not in methods:
        fail(f"required Stratum method missing: {method}")

rehearsal = matrix.get("release_rehearsal", {})
for key in (
    "verify_archive_sidecar",
    "verify_internal_sha256sums",
    "verify_release_manifest",
    "preserve_datadir_across_reinstall",
    "preserve_chain_tip_across_reinstall",
    "preserve_wallet_across_reinstall",
    "preserve_pool_ledger_across_reinstall",
    "post_upgrade_mining_required",
):
    if rehearsal.get(key) is not True:
        fail(f"release rehearsal safety requirement must remain true: {key}")
if rehearsal.get("first_package_version") == rehearsal.get("upgrade_package_version"):
    fail("release rehearsal package versions must differ")

scope = matrix.get("scope", {})
if scope.get("mainnet_activation") is not False:
    fail("CRAK-029 must not activate mainnet")
if scope.get("external_third_party_miner_certification") is not False:
    fail("CRAK-029 must not claim third-party miner certification")
if scope.get("real_public_testnet_evidence_required_separately") is not True:
    fail("real public-testnet evidence must remain a separate requirement")

require_text(
    "tests/interop_protocol_probe.py",
    [
        "mining.subscribe",
        "mining.authorize",
        "mining.set_difficulty",
        "mining.notify",
        "mining.suggest_difficulty",
        "independent Stratum interoperability: OK",
    ],
)
require_text(
    "tests/release_rehearsal_smoke.sh",
    [
        "ci-rehearsal-a",
        "ci-rehearsal-b",
        "release/INTEROP_MATRIX.json",
        "scripts/release-trust.py manifest",
        "scripts/release-trust.py verify",
        "interop_protocol_probe.py",
        "crakminer-native",
        "crakminer-stratum",
        "upgrade preserved chain tip",
        "CRAK-029 release rehearsal: OK",
    ],
)
require_text(
    ".github/workflows/verify-interoperability.yml",
    [
        "runner: ubuntu-24.04",
        "runner: ubuntu-24.04-arm",
        "expected_arch: x86_64",
        "expected_arch: arm64",
        "tests/release_rehearsal_smoke.sh",
        "scripts/verify-interop-integrity.py",
        "CRAK-029 native package interoperability and release rehearsal",
    ],
)
require_text(
    "scripts/package-linux.sh",
    [
        "docs/CRAK-029.md",
        "release/INTEROP_MATRIX.json",
        "INTEROP_MATRIX.json",
    ],
)
require_text(
    "docs/PROJECT_STATE.md",
    [
        "## Miner/node interoperability and release rehearsal — CRAK-029",
        "independent Stratum JSON client",
        "x86_64",
        "ARM64",
        "does not certify arbitrary third-party miners",
    ],
)

if errors:
    for error in errors:
        print(f"CRAK-029 integrity: ERROR: {error}", file=sys.stderr)
    raise SystemExit(1)

print("CRAK-029 interoperability integrity: OK")
