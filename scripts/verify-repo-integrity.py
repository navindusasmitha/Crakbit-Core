#!/usr/bin/env python3
"""CRAK-021 repository/release integrity gate.

This fast, dependency-free verifier keeps the default-branch engineering path
coherent. It checks that the current official payout toolchain, docs, package
wiring and CI workflows stay present, and rejects known legacy/conflicting
artifacts or migration-era branding from being reintroduced into the tracked
source surface.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def require(path: str) -> Path:
    p = ROOT / path
    if not p.exists():
        fail(f"missing required path: {path}")
    return p


def require_text(path: str, needles: list[str]) -> None:
    p = require(path)
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            fail(f"{path} missing required reference: {needle}")


REQUIRED_PATHS = [
    "README.md",
    "SOURCE_LOCK.json",
    "docs/BUILD.md",
    "docs/CONSENSUS.md",
    "docs/POOL.md",
    "docs/CRAK-018.md",
    "docs/CRAK-019.md",
    "docs/CRAK-020.md",
    "docs/CRAK-021.md",
    "docs/PROJECT_STATE.md",
    "scripts/crakpool-accounting.py",
    "scripts/crakpool-payout.py",
    "scripts/crakpool-paytx.py",
    "scripts/crakpool-payguard.py",
    "scripts/crakpool-payops.py",
    "scripts/package-linux.sh",
    "scripts/install-package.sh",
    "tests/pool_accounting_unit.py",
    "tests/payout_planner_unit.py",
    "tests/paytx_unit.py",
    "tests/payguard_unit.py",
    "tests/payops_unit.py",
    "tests/accounting_pool_smoke.sh",
    "tests/payout_planner_smoke.sh",
    "tests/payout_e2e_smoke.sh",
    ".github/workflows/verify-accounting.yml",
    ".github/workflows/verify-payout.yml",
    ".github/workflows/verify-paytx.yml",
    ".github/workflows/verify-payguard.yml",
    ".github/workflows/verify-payops.yml",
    ".github/workflows/verify-payout-e2e.yml",
    ".github/workflows/verify-repo-integrity.yml",
    ".github/workflows/verify.yml",
]

for required in REQUIRED_PATHS:
    require(required)

# The current default-branch custody design is CRAK-017/018: create an unsigned
# funded PSBT, preflight it, sign/broadcast externally, then attach the txid.
# A second in-repo signed/broadcast executor would create two competing payout
# state machines, so it is explicitly forbidden on the official main path.
FORBIDDEN_PATHS = [
    "scripts/crakpool-pay.py",
]
for forbidden in FORBIDDEN_PATHS:
    if (ROOT / forbidden).exists():
        fail(f"forbidden conflicting official-path artifact present: {forbidden}")

PACKAGE_HELPERS = [
    "crakpool-accounting.py",
    "crakpool-payout.py",
    "crakpool-paytx.py",
    "crakpool-payguard.py",
    "crakpool-payops.py",
]
require_text("scripts/package-linux.sh", PACKAGE_HELPERS)
require_text(
    "scripts/package-linux.sh",
    [
        "docs/CRAK-018.md",
        "docs/CRAK-019.md",
        "docs/CRAK-020.md",
        "docs/CRAK-021.md",
        "docs/PROJECT_STATE.md",
    ],
)

INSTALLED_COMMANDS = [
    "crakpool",
    "crakpool-payout",
    "crakpool-paytx",
    "crakpool-payguard",
    "crakpool-payops",
]
require_text("scripts/install-package.sh", INSTALLED_COMMANDS)

# Keep expensive workflows from running twice on feature branch updates.
# Feature work is tested by pull_request; push is main-only.
for workflow in (
    ".github/workflows/verify-payout-e2e.yml",
    ".github/workflows/verify-repo-integrity.yml",
    ".github/workflows/verify.yml",
):
    require_text(workflow, ["push:\n    branches:\n      - main", "pull_request:"])

# The full v0.1 gate must fail fast on the current payout state-machine tests
# and repository-integrity policy before spending time on a full node build.
require_text(
    ".github/workflows/verify.yml",
    [
        "python3 scripts/verify-repo-integrity.py",
        "scripts/crakpool-paytx.py",
        "scripts/crakpool-payguard.py",
        "scripts/crakpool-payops.py",
        "tests/paytx_unit.py",
        "tests/payguard_unit.py",
        "tests/payops_unit.py",
        "tests/payout_e2e_smoke.sh",
    ],
)

# Prevent migration-era branding from silently returning to maintained product
# source/docs. The CRAK-021 policy files are excluded because they intentionally
# document the term being prohibited. Git history and upstream material are not
# scanned; this gate checks the maintained proposed-main tree only.
legacy_brand = re.compile(r"(?i)(?:\bwamcoin\b|\bwam\s+coin\b|wam-coin|\bwam\b)")
policy_exclusions = {
    Path("scripts/verify-repo-integrity.py"),
    Path("docs/CRAK-021.md"),
    Path("docs/PROJECT_STATE.md"),
}
scan_roots = [ROOT / p for p in ("README.md", "docs", "scripts", "tests", ".github/workflows", "consensus", "src")]
text_suffixes = {".md", ".py", ".sh", ".yml", ".yaml", ".json", ".txt", ".cmake", ".cpp", ".cc", ".c", ".h", ".hpp"}

for scan_root in scan_roots:
    if scan_root.is_file():
        candidates = [scan_root]
    elif scan_root.is_dir():
        candidates = [p for p in scan_root.rglob("*") if p.is_file()]
    else:
        continue
    for path in candidates:
        rel = path.relative_to(ROOT)
        if rel in policy_exclusions:
            continue
        if path.suffix.lower() not in text_suffixes and path.name not in {"README", "CMakeLists.txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        match = legacy_brand.search(text)
        if match:
            fail(f"legacy migration branding found in maintained file {rel}: {match.group(0)!r}")

if errors:
    print("CRAK-021 repository integrity: FAILED", file=sys.stderr)
    for item in errors:
        print(f" - {item}", file=sys.stderr)
    raise SystemExit(1)

print(
    "CRAK-021 repository integrity: OK "
    "official_payout_path=planner+paytx+payguard+payops "
    "legacy_executor=absent package_wiring=ok workflows=ok branding=ok"
)
