#!/usr/bin/env python3
"""CRAK-028 fail-closed pool perimeter security integrity gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def require(path: str) -> Path:
    p = ROOT / path
    if not p.is_file():
        fail(f"missing required file: {path}")
    return p


def require_text(path: str, needles: list[str]) -> None:
    p = require(path)
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            fail(f"{path} missing required security contract: {needle}")


for path in [
    "network/POOL_SECURITY.json",
    "scripts/crakpool-edge.py",
    "scripts/crakminer-stratum.py",
    "scripts/verify-pool-security-integrity.py",
    "tests/pool_security_unit.py",
    "docs/CRAK-028.md",
    "docs/POOL_SECURITY.md",
    ".github/workflows/verify-pool-security.yml",
]:
    require(path)

try:
    policy = json.loads((ROOT / "network/POOL_SECURITY.json").read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"unable to parse pool security policy: {exc}")
    policy = {}

transport = policy.get("transport", {})
auth = policy.get("authentication", {})
limits = policy.get("limits", {})
logging = policy.get("logging", {})

checks = [
    (policy.get("schema") == 1, "POOL_SECURITY schema must be 1"),
    (transport.get("public_tls_required") is True, "public TLS must remain required"),
    (transport.get("minimum_tls_version") == "TLSv1.2", "minimum TLS must remain TLSv1.2"),
    (transport.get("upstream_loopback_required") is True, "edge upstream must remain loopback-only"),
    (auth.get("worker_auth_required") is True, "worker authentication must remain required"),
    (auth.get("kdf") == "pbkdf2-hmac-sha256", "worker KDF must remain PBKDF2-HMAC-SHA256"),
    (int(auth.get("iterations", 0)) >= 200_000, "PBKDF2 iterations below 200000"),
    (int(auth.get("salt_bytes", 0)) >= 16, "credential salt below 16 bytes"),
    (0 < int(auth.get("max_worker_length", 0)) <= 128, "worker length ceiling weakened"),
    (0 < int(auth.get("max_failures_per_window", 0)) <= 5, "auth failure threshold weakened"),
    (0 < int(auth.get("failure_window_seconds", 0)) <= 300, "auth failure window weakened"),
    (int(auth.get("ban_seconds", 0)) >= 300, "auth-failure ban duration weakened"),
    (0 < int(limits.get("max_connections", 0)) <= 1024, "global connection cap weakened"),
    (0 < int(limits.get("max_connections_per_ip", 0)) <= 16, "per-IP connection cap weakened"),
    (1024 <= int(limits.get("max_line_bytes", 0)) <= 16384, "Stratum line-size ceiling weakened"),
    (0 < int(limits.get("auth_timeout_seconds", 0)) <= 20, "authorization timeout weakened"),
    (0 < int(limits.get("idle_timeout_seconds", 0)) <= 180, "idle timeout weakened"),
    (0 < float(limits.get("message_rate_per_second", 0)) <= 30, "message rate limit weakened"),
    (0 < float(limits.get("message_burst", 0)) <= 60, "message burst limit weakened"),
    (0 < float(limits.get("submit_rate_per_second", 0)) <= 6, "per-session submit rate weakened"),
    (0 < float(limits.get("submit_burst", 0)) <= 12, "per-session submit burst weakened"),
    (0 < float(limits.get("global_submit_rate_per_second", 0)) <= 24, "global submit rate weakened"),
    (0 < float(limits.get("global_submit_burst", 0)) <= 48, "global submit burst weakened"),
    (logging.get("structured_security_events") is True, "structured security events must remain enabled"),
    (logging.get("log_secrets") is False, "security logging must never log secrets"),
]
for ok, msg in checks:
    if not ok:
        fail(msg)

require_text("scripts/crakpool-edge.py", [
    "ssl.TLSVersion.TLSv1_2",
    "hashlib.pbkdf2_hmac",
    "hmac.compare_digest",
    "edge-authenticated",
    "upstream loopback",
    "message_rate_limit",
    "submit_rate_limit",
    "submit_identity_mismatch",
    "ip_banned",
    "require_private_file",
    "ALLOWED_METHODS",
])
require_text("scripts/crakminer-stratum.py", [
    "ssl.TLSVersion.TLSv1_2",
    "ssl.CERT_REQUIRED",
    "--password-file",
    "--password-stdin",
    "--tls-ca-file",
    "password file must not be group/world-readable",
])
require_text("tests/pool_security_unit.py", [
    "public plaintext bind was accepted",
    "non-loopback upstream was accepted",
    "edge-authenticated",
    "submit",
    "ssl.CERT_REQUIRED",
    "bad credential leaked to upstream",
])
require_text(".github/workflows/verify-pool-security.yml", [
    "tests/pool_security_unit.py",
    "tests/stratum_protocol_unit.py",
    "scripts/verify-pool-security-integrity.py",
    "push:\n    branches:\n      - main",
    "pull_request:",
])

if errors:
    print("CRAK-028 pool security integrity: FAILED", file=sys.stderr)
    for item in errors:
        print(f" - {item}", file=sys.stderr)
    raise SystemExit(1)

print(
    "CRAK-028 pool security integrity: OK "
    "tls=required auth=required upstream=loopback rate_limits=locked secrets=redacted"
)
