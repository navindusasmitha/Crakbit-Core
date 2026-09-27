#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "security-review-gate.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("crak_security_review_gate", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {TOOL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = load_gate()
POLICY = gate.load_json(ROOT / "security" / "SECURITY_REVIEW_POLICY.json")
STATUS = gate.load_json(ROOT / "security" / "SECURITY_REVIEW_STATUS.json")
REGISTRY = gate.load_json(ROOT / "security" / "SECURITY_FINDINGS.json")
HEAD = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()


def complete_status() -> dict:
    status = copy.deepcopy(STATUS)
    status.update(
        {
            "review_state": "complete",
            "independent_external_review_complete": True,
            "independence_attested": True,
            "reviewed_commit": HEAD,
            "review_completed_at": "2026-09-27T00:00:00Z",
            "report_sha256": "a" * 64,
            "report_reference": "operator-held:external-security-review-v1",
            "reviewers": [
                {
                    "reviewer_id": "external-reviewer-1",
                    "organization": "Independent Security Reviewer",
                    "independent_from_project": True,
                }
            ],
            "scope_coverage": list(POLICY["required_scopes"]),
        }
    )
    return status


def finding(
    severity: str,
    status: str,
    *,
    material: bool | None = None,
    fid: str = "CRAK-SEC-2026-001",
) -> dict:
    if material is None:
        material = severity in {"critical", "high"}
    item = {
        "id": fid,
        "title": "Synthetic regression finding",
        "area": "release-supply-chain-and-signing",
        "description": "Synthetic CRAK-030 unit-test finding.",
        "severity": severity,
        "material": material,
        "status": status,
    }
    if status == "verified_remediated":
        item["remediation"] = {"commit": "b" * 40, "summary": "synthetic fix"}
        item["verification"] = {
            "independent_retest": True,
            "reviewer_id": "external-reviewer-1",
            "verified_at": "2026-09-27T01:00:00Z",
            "evidence_sha256": "c" * 64,
        }
    if status == "risk_accepted":
        item["risk_acceptance"] = {
            "approved_by": "release-owner",
            "reason": "synthetic non-material test case",
            "expires_at": "2099-01-01T00:00:00Z",
        }
    return item


def assert_valid(policy: dict, status: dict, registry: dict) -> None:
    errors = gate.validate_all(policy, status, registry)
    assert not errors, errors


def main() -> None:
    # The checked-in baseline must be structurally valid but intentionally launch-blocked.
    assert_valid(POLICY, STATUS, REGISTRY)
    baseline = gate.launch_blockers(POLICY, STATUS, REGISTRY, HEAD, check_git=False)
    assert any("review is not complete" in item for item in baseline), baseline

    # A complete independent review with full scope and no findings can authorize a candidate.
    good_status = complete_status()
    empty = copy.deepcopy(REGISTRY)
    assert_valid(POLICY, good_status, empty)
    assert gate.launch_blockers(POLICY, good_status, empty, HEAD, check_git=False) == []

    # Critical/high findings are always material and cannot be risk accepted.
    critical_open = {**REGISTRY, "findings": [finding("critical", "open")]}
    assert_valid(POLICY, good_status, critical_open)
    blockers = gate.launch_blockers(POLICY, good_status, critical_open, HEAD, check_git=False)
    assert any("material finding not verified remediated" in item for item in blockers), blockers

    high_accepted = {**REGISTRY, "findings": [finding("high", "risk_accepted")]}
    errors = gate.validate_all(POLICY, good_status, high_accepted)
    assert any("forbids risk acceptance" in item for item in errors), errors

    # A material medium finding also requires verified remediation.
    medium_material = {**REGISTRY, "findings": [finding("medium", "open", material=True)]}
    assert_valid(POLICY, good_status, medium_material)
    blockers = gate.launch_blockers(POLICY, good_status, medium_material, HEAD, check_git=False)
    assert blockers, blockers

    medium_material_accepted = {**REGISTRY, "findings": [finding("medium", "risk_accepted", material=True)]}
    errors = gate.validate_all(POLICY, good_status, medium_material_accepted)
    assert any("material finding cannot be risk accepted" in item for item in errors), errors

    # Non-material medium/low risk acceptance is allowed only while unexpired.
    medium_accepted = {**REGISTRY, "findings": [finding("medium", "risk_accepted", material=False)]}
    assert_valid(POLICY, good_status, medium_accepted)
    blockers = gate.launch_blockers(
        POLICY,
        good_status,
        medium_accepted,
        HEAD,
        check_git=False,
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    assert not blockers, blockers
    expired = copy.deepcopy(medium_accepted)
    expired["findings"][0]["risk_acceptance"]["expires_at"] = "2020-01-01T00:00:00Z"
    blockers = gate.launch_blockers(
        POLICY,
        good_status,
        expired,
        HEAD,
        check_git=False,
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    assert any("risk acceptance expired" in item for item in blockers), blockers

    # Verified independent remediation clears a material finding.
    fixed = {**REGISTRY, "findings": [finding("critical", "verified_remediated")]}
    assert_valid(POLICY, good_status, fixed)
    assert gate.launch_blockers(POLICY, good_status, fixed, HEAD, check_git=False) == []

    # Full scope, report digest and reviewer independence are fail-closed requirements.
    missing_scope = complete_status()
    missing_scope["scope_coverage"] = missing_scope["scope_coverage"][:-1]
    errors = gate.validate_all(POLICY, missing_scope, REGISTRY)
    assert any("missing required scopes" in item for item in errors), errors

    bad_report = complete_status()
    bad_report["report_sha256"] = "not-a-digest"
    errors = gate.validate_all(POLICY, bad_report, REGISTRY)
    assert any("report_sha256" in item for item in errors), errors

    dependent = complete_status()
    dependent["reviewers"][0]["independent_from_project"] = False
    errors = gate.validate_all(POLICY, dependent, REGISTRY)
    assert any("independent_from_project" in item for item in errors), errors

    print("CRAK-030 security review gate unit: OK")


if __name__ == "__main__":
    main()
