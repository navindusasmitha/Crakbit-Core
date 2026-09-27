#!/usr/bin/env python3
"""CRAK-030 external security review and remediation launch gate.

This tool validates the checked-in review policy/status/findings registry and can
fail closed for a release candidate until an independent external review is
complete and all material findings are independently re-tested as remediated.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SEVERITIES = {"critical", "high", "medium", "low", "informational"}


class GateError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"unable to load JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GateError(f"JSON root must be an object: {path}")
    return data


def parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise GateError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise GateError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema") != 1:
        errors.append("policy schema must be 1")
    if policy.get("milestone") != "CRAK-030":
        errors.append("policy milestone must be CRAK-030")
    if policy.get("project") != "Crakbit Core":
        errors.append("policy project must be Crakbit Core")
    if policy.get("repository") != "navindusasmitha/Crakbit-Core":
        errors.append("policy repository identity mismatch")

    scopes = policy.get("required_scopes")
    if not isinstance(scopes, list) or len(scopes) < 8 or len(scopes) != len(set(scopes)):
        errors.append("policy required_scopes must contain at least 8 unique entries")

    severity = policy.get("severity_policy", {})
    if set(severity) != SEVERITIES:
        errors.append("policy severity_policy must define exactly critical/high/medium/low/informational")
    for level in ("critical", "high"):
        entry = severity.get(level, {})
        if entry.get("material") is not True:
            errors.append(f"{level} severity must always be material")
        if entry.get("risk_acceptance_allowed") is not False:
            errors.append(f"{level} severity must forbid risk acceptance")

    statuses = policy.get("finding_statuses")
    required_statuses = {"open", "remediated_pending_retest", "verified_remediated", "risk_accepted"}
    if not isinstance(statuses, list) or set(statuses) != required_statuses:
        errors.append("policy finding_statuses do not match the CRAK-030 state machine")

    launch = policy.get("launch_requirements", {})
    for key in (
        "independent_external_review_complete",
        "independence_attestation_required",
        "report_sha256_required",
        "full_scope_coverage_required",
        "all_material_findings_verified_remediated",
        "critical_and_high_risk_acceptance_forbidden",
        "expired_risk_acceptance_forbidden",
        "reviewed_commit_must_be_ancestor",
        "post_review_code_drift_forbidden",
    ):
        if launch.get(key) is not True:
            errors.append(f"launch requirement must remain true: {key}")
    allowed = launch.get("allowed_post_review_paths")
    if not isinstance(allowed, list) or not allowed:
        errors.append("allowed_post_review_paths must be a non-empty list")
    return errors


def validate_status(status: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if status.get("schema") != 1 or status.get("milestone") != "CRAK-030":
        errors.append("review status schema/milestone mismatch")
    if status.get("project") != "Crakbit Core":
        errors.append("review status project mismatch")
    state = status.get("review_state")
    if state not in {"not_performed", "in_progress", "complete"}:
        errors.append("review_state must be not_performed, in_progress, or complete")

    if state != "complete":
        if status.get("independent_external_review_complete") is not False:
            errors.append("incomplete review must set independent_external_review_complete=false")
        return errors

    if status.get("independent_external_review_complete") is not True:
        errors.append("complete review must set independent_external_review_complete=true")
    if status.get("independence_attested") is not True:
        errors.append("complete review must include independence_attested=true")
    reviewed = status.get("reviewed_commit")
    if not isinstance(reviewed, str) or not HEX40.fullmatch(reviewed.lower()):
        errors.append("complete review requires a 40-hex reviewed_commit")
    report = status.get("report_sha256")
    if not isinstance(report, str) or not HEX64.fullmatch(report.lower()):
        errors.append("complete review requires a 64-hex report_sha256")
    if not isinstance(status.get("report_reference"), str) or not status.get("report_reference", "").strip():
        errors.append("complete review requires a non-empty report_reference")
    completed = status.get("review_completed_at")
    if not isinstance(completed, str):
        errors.append("complete review requires review_completed_at")
    else:
        try:
            parse_time(completed, "review_completed_at")
        except GateError as exc:
            errors.append(str(exc))

    reviewers = status.get("reviewers")
    if not isinstance(reviewers, list) or not reviewers:
        errors.append("complete review requires at least one reviewer record")
    else:
        for idx, reviewer in enumerate(reviewers):
            if not isinstance(reviewer, dict):
                errors.append(f"reviewer[{idx}] must be an object")
                continue
            if not str(reviewer.get("reviewer_id", "")).strip():
                errors.append(f"reviewer[{idx}] missing reviewer_id")
            if not str(reviewer.get("organization", "")).strip():
                errors.append(f"reviewer[{idx}] missing organization")
            if reviewer.get("independent_from_project") is not True:
                errors.append(f"reviewer[{idx}] must attest independent_from_project=true")

    required_scopes = set(policy.get("required_scopes", []))
    coverage = status.get("scope_coverage")
    if not isinstance(coverage, list):
        errors.append("scope_coverage must be a list")
    else:
        missing = sorted(required_scopes - set(coverage))
        if missing:
            errors.append("complete review missing required scopes: " + ", ".join(missing))
    return errors


def validate_findings(registry: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema") != 1 or registry.get("milestone") != "CRAK-030":
        errors.append("findings registry schema/milestone mismatch")
    if registry.get("project") != "Crakbit Core":
        errors.append("findings registry project mismatch")
    findings = registry.get("findings")
    if not isinstance(findings, list):
        return errors + ["findings must be a list"]

    seen: set[str] = set()
    severity_policy = policy.get("severity_policy", {})
    valid_statuses = set(policy.get("finding_statuses", []))
    for idx, finding in enumerate(findings):
        prefix = f"finding[{idx}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object")
            continue
        fid = str(finding.get("id", ""))
        if not re.fullmatch(r"CRAK-SEC-[0-9]{4}-[0-9]{3}", fid):
            errors.append(f"{prefix} id must match CRAK-SEC-YYYY-NNN")
        elif fid in seen:
            errors.append(f"duplicate finding id: {fid}")
        seen.add(fid)
        for required in ("title", "area", "description"):
            if not str(finding.get(required, "")).strip():
                errors.append(f"{fid or prefix} missing {required}")
        level = finding.get("severity")
        if level not in SEVERITIES:
            errors.append(f"{fid or prefix} invalid severity")
            continue
        material = finding.get("material")
        if not isinstance(material, bool):
            errors.append(f"{fid or prefix} material must be boolean")
        if level in {"critical", "high"} and material is not True:
            errors.append(f"{fid or prefix} {level} finding must be material")
        state = finding.get("status")
        if state not in valid_statuses:
            errors.append(f"{fid or prefix} invalid status")
            continue

        if state == "verified_remediated":
            remediation = finding.get("remediation", {})
            verification = finding.get("verification", {})
            commit = str(remediation.get("commit", "")).lower()
            if not HEX40.fullmatch(commit):
                errors.append(f"{fid or prefix} verified remediation requires 40-hex remediation.commit")
            if verification.get("independent_retest") is not True:
                errors.append(f"{fid or prefix} verified remediation requires independent_retest=true")
            if not str(verification.get("reviewer_id", "")).strip():
                errors.append(f"{fid or prefix} verified remediation missing verification.reviewer_id")
            digest = str(verification.get("evidence_sha256", "")).lower()
            if not HEX64.fullmatch(digest):
                errors.append(f"{fid or prefix} verified remediation requires 64-hex evidence_sha256")
            try:
                parse_time(str(verification.get("verified_at", "")), f"{fid}.verification.verified_at")
            except GateError as exc:
                errors.append(str(exc))

        if state == "risk_accepted":
            if not severity_policy.get(level, {}).get("risk_acceptance_allowed", False):
                errors.append(f"{fid or prefix} severity {level} forbids risk acceptance")
            if material is True:
                errors.append(f"{fid or prefix} material finding cannot be risk accepted")
            acceptance = finding.get("risk_acceptance", {})
            if not str(acceptance.get("approved_by", "")).strip():
                errors.append(f"{fid or prefix} risk acceptance missing approved_by")
            if not str(acceptance.get("reason", "")).strip():
                errors.append(f"{fid or prefix} risk acceptance missing reason")
            try:
                parse_time(str(acceptance.get("expires_at", "")), f"{fid}.risk_acceptance.expires_at")
            except GateError as exc:
                errors.append(str(exc))
    return errors


def git_output(args: list[str]) -> str:
    p = subprocess.run(["git", "-C", str(ROOT), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise GateError(p.stderr.strip() or p.stdout.strip() or f"git command failed: {' '.join(args)}")
    return p.stdout.strip()


def resolve_source_commit(explicit: str | None) -> str:
    if explicit:
        value = explicit.lower()
    else:
        value = git_output(["rev-parse", "HEAD"]).lower()
    if not HEX40.fullmatch(value):
        raise GateError("source commit must be exactly 40 hex characters")
    return value


def launch_blockers(
    policy: dict[str, Any],
    status: dict[str, Any],
    registry: dict[str, Any],
    source_commit: str,
    *,
    check_git: bool = True,
    now: datetime | None = None,
) -> list[str]:
    blockers: list[str] = []
    now = now or datetime.now(timezone.utc)
    if status.get("review_state") != "complete" or status.get("independent_external_review_complete") is not True:
        blockers.append("independent external security review is not complete")
        return blockers

    reviewed = str(status.get("reviewed_commit", "")).lower()
    if not HEX40.fullmatch(reviewed):
        blockers.append("reviewed_commit is invalid")
    elif check_git:
        ancestor = subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", reviewed, source_commit],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if ancestor.returncode != 0:
            blockers.append("reviewed_commit is not an ancestor of the release source commit")
        else:
            changed = git_output(["diff", "--name-only", reviewed, source_commit]).splitlines()
            allowed = set(policy.get("launch_requirements", {}).get("allowed_post_review_paths", []))
            drift = sorted(path for path in changed if path and path not in allowed)
            if drift:
                blockers.append("post-review code drift detected: " + ", ".join(drift))

    required_scopes = set(policy.get("required_scopes", []))
    covered = set(status.get("scope_coverage", []))
    missing = sorted(required_scopes - covered)
    if missing:
        blockers.append("required review scopes missing: " + ", ".join(missing))

    for finding in registry.get("findings", []):
        fid = str(finding.get("id", "unknown"))
        level = finding.get("severity")
        material = bool(finding.get("material")) or level in {"critical", "high"}
        state = finding.get("status")
        if material and state != "verified_remediated":
            blockers.append(f"material finding not verified remediated: {fid} ({level}/{state})")
        if state == "risk_accepted":
            acceptance = finding.get("risk_acceptance", {})
            try:
                expiry = parse_time(str(acceptance.get("expires_at", "")), f"{fid}.risk_acceptance.expires_at")
            except GateError:
                blockers.append(f"risk acceptance has invalid expiry: {fid}")
            else:
                if expiry <= now:
                    blockers.append(f"risk acceptance expired: {fid}")
    return blockers


def load_all(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        load_json(Path(args.policy)),
        load_json(Path(args.status_file)),
        load_json(Path(args.findings)),
    )


def validate_all(policy: dict[str, Any], status: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    return validate_policy(policy) + validate_status(status, policy) + validate_findings(registry, policy)


def summary(policy: dict[str, Any], status: dict[str, Any], registry: dict[str, Any], source_commit: str) -> dict[str, Any]:
    findings = registry.get("findings", [])
    counts = {level: 0 for level in sorted(SEVERITIES)}
    for finding in findings:
        level = finding.get("severity")
        if level in counts:
            counts[level] += 1
    blockers = launch_blockers(policy, status, registry, source_commit)
    return {
        "milestone": "CRAK-030",
        "source_commit": source_commit,
        "review_state": status.get("review_state"),
        "independent_external_review_complete": bool(status.get("independent_external_review_complete")),
        "finding_counts": counts,
        "launch_authorized": not blockers,
        "launch_blockers": blockers,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CRAK-030 external security review/remediation gate")
    p.add_argument("--policy", default=str(ROOT / "security" / "SECURITY_REVIEW_POLICY.json"))
    p.add_argument("--status-file", default=str(ROOT / "security" / "SECURITY_REVIEW_STATUS.json"))
    p.add_argument("--findings", default=str(ROOT / "security" / "SECURITY_FINDINGS.json"))
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate policy, review status and finding schemas")
    s = sub.add_parser("status", help="print review state and launch blockers without failing on blockers")
    s.add_argument("--source-commit")
    s.add_argument("--json", action="store_true")
    g = sub.add_parser("launch", help="fail closed unless CRAK-030 authorizes this source commit")
    g.add_argument("--source-commit")
    g.add_argument("--json", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    policy, status, registry = load_all(args)
    errors = validate_all(policy, status, registry)
    if errors:
        raise GateError("; ".join(errors))
    if args.command == "validate":
        print("CRAK-030 security review registry: OK")
        return 0
    source_commit = resolve_source_commit(args.source_commit)
    result = summary(policy, status, registry, source_commit)
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print(
            "CRAK-030 security review status: "
            f"state={result['review_state']} findings={sum(result['finding_counts'].values())} "
            f"launch_authorized={str(result['launch_authorized']).lower()}"
        )
        for blocker in result["launch_blockers"]:
            print(f"BLOCKER: {blocker}")
    if args.command == "launch" and not result["launch_authorized"]:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GateError, OSError) as exc:
        print(f"CRAK-030 security review gate: FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
