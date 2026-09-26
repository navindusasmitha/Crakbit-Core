#!/usr/bin/env python3
"""CRAK-028 hardened internet-facing Stratum edge.

The accounting pool and crakbitd RPC stay private on loopback. This edge is the
only CRAK-028 component intended to accept public miner connections.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import ssl
import stat
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_METHODS = {
    "mining.subscribe", "mining.authorize", "mining.submit",
    "mining.extranonce.subscribe", "mining.suggest_difficulty",
}


def default_policy_path() -> Path:
    if os.environ.get("CRAKBIT_POOL_SECURITY_POLICY"):
        return Path(os.environ["CRAKBIT_POOL_SECURITY_POLICY"])
    here = Path(__file__).resolve()
    for p in (
        here.parent.parent / "network" / "POOL_SECURITY.json",
        here.parent.parent / "share" / "doc" / "crakbit-core" / "POOL_SECURITY.json",
        here.parent / "POOL_SECURITY.json",
    ):
        if p.exists():
            return p
    return here.parent.parent / "network" / "POOL_SECURITY.json"


def is_loopback_host(host: str) -> bool:
    text = host.strip().lower()
    if text in {"localhost", "ip6-localhost"}:
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def require_private_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError(f"{label} must not be group/world-readable: {path}")


@dataclass(frozen=True)
class SecurityPolicy:
    public_tls_required: bool
    minimum_tls_version: str
    upstream_loopback_required: bool
    worker_auth_required: bool
    kdf: str
    iterations: int
    salt_bytes: int
    max_worker_length: int
    worker_pattern: str
    max_failures_per_window: int
    failure_window_seconds: int
    ban_seconds: int
    max_connections: int
    max_connections_per_ip: int
    max_line_bytes: int
    auth_timeout_seconds: int
    idle_timeout_seconds: int
    message_rate_per_second: float
    message_burst: float
    submit_rate_per_second: float
    submit_burst: float
    global_submit_rate_per_second: float
    global_submit_burst: float
    upstream_connect_timeout_seconds: float
    tls_handshake_timeout_seconds: float
    structured_security_events: bool
    log_secrets: bool

    @classmethod
    def load(cls, path: Path) -> "SecurityPolicy":
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("schema") != 1:
            raise ValueError("POOL_SECURITY schema must be 1")
        t, a, l, g = d.get("transport", {}), d.get("authentication", {}), d.get("limits", {}), d.get("logging", {})
        p = cls(
            bool(t.get("public_tls_required")), str(t.get("minimum_tls_version", "")), bool(t.get("upstream_loopback_required")),
            bool(a.get("worker_auth_required")), str(a.get("kdf", "")), int(a.get("iterations", 0)), int(a.get("salt_bytes", 0)),
            int(a.get("max_worker_length", 0)), str(a.get("worker_pattern", "")), int(a.get("max_failures_per_window", 0)),
            int(a.get("failure_window_seconds", 0)), int(a.get("ban_seconds", 0)), int(l.get("max_connections", 0)),
            int(l.get("max_connections_per_ip", 0)), int(l.get("max_line_bytes", 0)), int(l.get("auth_timeout_seconds", 0)),
            int(l.get("idle_timeout_seconds", 0)), float(l.get("message_rate_per_second", 0)), float(l.get("message_burst", 0)),
            float(l.get("submit_rate_per_second", 0)), float(l.get("submit_burst", 0)), float(l.get("global_submit_rate_per_second", 0)),
            float(l.get("global_submit_burst", 0)), float(l.get("upstream_connect_timeout_seconds", 0)),
            float(l.get("tls_handshake_timeout_seconds", 0)), bool(g.get("structured_security_events")), bool(g.get("log_secrets")),
        )
        p.validate()
        return p

    def validate(self) -> None:
        if not self.public_tls_required or self.minimum_tls_version != "TLSv1.2":
            raise ValueError("public TLS 1.2+ must be required")
        if not self.upstream_loopback_required:
            raise ValueError("upstream loopback must be required")
        if not self.worker_auth_required or self.kdf != "pbkdf2-hmac-sha256":
            raise ValueError("worker PBKDF2 authentication must be required")
        if self.iterations < 200_000 or self.salt_bytes < 16:
            raise ValueError("worker credential KDF below CRAK-028 floor")
        if not 1 <= self.max_worker_length <= 128:
            raise ValueError("invalid max_worker_length")
        re.compile(self.worker_pattern)
        ints = [self.max_failures_per_window, self.failure_window_seconds, self.ban_seconds, self.max_connections,
                self.max_connections_per_ip, self.max_line_bytes, self.auth_timeout_seconds, self.idle_timeout_seconds]
        floats = [self.message_rate_per_second, self.message_burst, self.submit_rate_per_second, self.submit_burst,
                  self.global_submit_rate_per_second, self.global_submit_burst, self.upstream_connect_timeout_seconds,
                  self.tls_handshake_timeout_seconds]
        if any(v <= 0 for v in ints + floats):
            raise ValueError("all security limits must be positive")
        if self.max_connections_per_ip > self.max_connections or not 1024 <= self.max_line_bytes <= 65536:
            raise ValueError("invalid connection/line limits")
        if self.log_secrets:
            raise ValueError("security logs must never log secrets")


def valid_worker_name(worker: str, policy: SecurityPolicy) -> bool:
    return 0 < len(worker) <= policy.max_worker_length and re.fullmatch(policy.worker_pattern, worker) is not None


def derive_secret(secret: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, iterations, dklen=32)


def write_worker_credential(path: Path, worker: str, secret: str, policy: SecurityPolicy) -> None:
    if not valid_worker_name(worker, policy) or not secret:
        raise ValueError("invalid worker name or empty secret")
    if path.exists():
        require_private_file(path, "worker credential file")
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"schema": 1, "kdf": policy.kdf, "iterations": policy.iterations, "workers": {}}
    if data.get("schema") != 1 or data.get("kdf") != policy.kdf or int(data.get("iterations", 0)) != policy.iterations:
        raise ValueError("incompatible worker credential file")
    if not isinstance(data.get("workers"), dict):
        raise ValueError("worker credential workers must be an object")
    salt = secrets.token_bytes(policy.salt_bytes)
    data["workers"][worker] = {"enabled": True, "salt": salt.hex(), "digest": derive_secret(secret, salt, policy.iterations).hex()}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, sort_keys=True, indent=2)
        f.write("\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    if os.name == "posix": os.chmod(path, 0o600)


class WorkerAuth:
    def __init__(self, path: Path, policy: SecurityPolicy):
        require_private_file(path, "worker credential file")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != 1 or data.get("kdf") != policy.kdf or int(data.get("iterations", 0)) != policy.iterations:
            raise ValueError("worker credential file does not match policy")
        if not isinstance(data.get("workers"), dict):
            raise ValueError("worker credential workers must be an object")
        self.policy, self.workers = policy, data["workers"]

    def verify(self, worker: str, secret: str) -> bool:
        if not valid_worker_name(worker, self.policy):
            return False
        rec = self.workers.get(worker)
        if not isinstance(rec, dict) or rec.get("enabled") is not True:
            salt = b"\x00" * self.policy.salt_bytes
            hmac.compare_digest(derive_secret(secret, salt, self.policy.iterations), b"\x00" * 32)
            return False
        try:
            salt, expected = bytes.fromhex(str(rec["salt"])), bytes.fromhex(str(rec["digest"]))
        except (KeyError, ValueError):
            return False
        return hmac.compare_digest(derive_secret(secret, salt, self.policy.iterations), expected)


class TokenBucket:
    def __init__(self, rate: float, burst: float):
        self.rate, self.burst, self.tokens, self.updated = rate, burst, burst, time.monotonic()

    def consume(self, amount: float = 1.0, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        self.tokens = min(self.burst, self.tokens + max(0.0, now - self.updated) * self.rate)
        self.updated = now
        if self.tokens < amount: return False
        self.tokens -= amount
        return True


class AbuseGuard:
    def __init__(self, policy: SecurityPolicy):
        self.p = policy; self.total = 0; self.per_ip: dict[str, int] = defaultdict(int)
        self.failures: dict[str, deque[float]] = defaultdict(deque); self.banned_until: dict[str, float] = {}

    def is_banned(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return self.banned_until.get(ip, 0.0) > now

    def admit(self, ip: str) -> tuple[bool, str]:
        if self.is_banned(ip): return False, "ip_banned"
        if self.total >= self.p.max_connections: return False, "global_connection_limit"
        if self.per_ip[ip] >= self.p.max_connections_per_ip: return False, "per_ip_connection_limit"
        self.total += 1; self.per_ip[ip] += 1
        return True, "ok"

    def release(self, ip: str) -> None:
        self.total = max(0, self.total - 1); self.per_ip[ip] = max(0, self.per_ip[ip] - 1)

    def record_auth_failure(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self.failures[ip]; cutoff = now - self.p.failure_window_seconds
        while q and q[0] < cutoff: q.popleft()
        q.append(now)
        if len(q) >= self.p.max_failures_per_window:
            self.banned_until[ip] = now + self.p.ban_seconds; q.clear(); return True
        return False

    def clear_failures(self, ip: str) -> None:
        self.failures.pop(ip, None)


class SecurityLogger:
    def __init__(self, path: Path | None): self.path = path
    def emit(self, event: str, **fields: Any) -> None:
        rec = {"event": event, "ts": int(time.time()), **{k: v for k, v in fields.items() if v not in (None, "")}}
        line = "crakpool-security " + json.dumps(rec, sort_keys=True, separators=(",", ":"))
        print(line, file=sys.stderr, flush=True)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f: f.write(json.dumps(rec, sort_keys=True) + "\n")


def build_tls_context(cert: Path | None, key: Path | None) -> ssl.SSLContext | None:
    if bool(cert) != bool(key): raise ValueError("--tls-cert and --tls-key must be supplied together")
    if not cert: return None
    assert key is not None
    if not cert.is_file(): raise ValueError(f"TLS certificate not found: {cert}")
    require_private_file(key, "TLS private key")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert), str(key)); return ctx


def validate_serve_config(listen: str, upstream_host: str, tls: ssl.SSLContext | None, auth: WorkerAuth, policy: SecurityPolicy) -> None:
    if policy.upstream_loopback_required and not is_loopback_host(upstream_host): raise ValueError("upstream loopback is required")
    if policy.worker_auth_required and auth is None: raise ValueError("worker credential file is required")
    if not is_loopback_host(listen) and policy.public_tls_required and tls is None: raise ValueError("public Stratum bind requires TLS")


@dataclass
class EdgeSession:
    peer_ip: str
    message_bucket: TokenBucket
    submit_bucket: TokenBucket
    subscribed: bool = False
    authorized: bool = False
    worker: str = ""


class EdgeGateway:
    def __init__(self, policy: SecurityPolicy, auth: WorkerAuth, listen: str, port: int, upstream_host: str, upstream_port: int,
                 tls_context: ssl.SSLContext | None, security_log: Path | None):
        validate_serve_config(listen, upstream_host, tls_context, auth, policy)
        self.policy, self.auth, self.listen, self.port = policy, auth, listen, port
        self.upstream_host, self.upstream_port, self.tls_context = upstream_host, upstream_port, tls_context
        self.guard, self.logger = AbuseGuard(policy), SecurityLogger(security_log)
        self.global_submit = TokenBucket(policy.global_submit_rate_per_second, policy.global_submit_burst)

    async def reply(self, w: asyncio.StreamWriter, rid: Any, result: Any = None, error: Any = None) -> None:
        w.write((json.dumps({"id": rid, "result": result, "error": error}, separators=(",", ":")) + "\n").encode()); await w.drain()

    async def read_line(self, r: asyncio.StreamReader, timeout: float) -> bytes:
        line = await asyncio.wait_for(r.readline(), timeout=timeout)
        if len(line) > self.policy.max_line_bytes: raise ValueError("line too large")
        return line

    async def client_to_upstream(self, s: EdgeSession, cr: asyncio.StreamReader, cw: asyncio.StreamWriter, uw: asyncio.StreamWriter) -> None:
        started = time.monotonic()
        while True:
            timeout = self.policy.idle_timeout_seconds
            if not s.authorized: timeout = min(timeout, max(0.1, self.policy.auth_timeout_seconds - (time.monotonic() - started)))
            try: line = await self.read_line(cr, timeout)
            except asyncio.TimeoutError:
                self.logger.emit("auth_timeout" if not s.authorized else "idle_timeout", peer_ip=s.peer_ip, worker=s.worker); return
            except ValueError:
                self.logger.emit("protocol_violation", peer_ip=s.peer_ip, reason="line_too_large"); return
            if not line: return
            if not s.message_bucket.consume(): self.logger.emit("message_rate_limit", peer_ip=s.peer_ip, worker=s.worker); return
            try: msg = json.loads(line)
            except json.JSONDecodeError:
                await self.reply(cw, None, None, [20, "invalid JSON", None]); continue
            if not isinstance(msg, dict): await self.reply(cw, None, None, [20, "request is not an object", None]); continue
            rid, method, params = msg.get("id"), msg.get("method"), msg.get("params", [])
            if not isinstance(method, str) or method not in ALLOWED_METHODS:
                self.logger.emit("protocol_violation", peer_ip=s.peer_ip, reason="unsupported Stratum method")
                await self.reply(cw, rid, False, [20, "unsupported method", None]); continue
            if not isinstance(params, list): await self.reply(cw, rid, False, [20, "params must be an array", None]); continue
            if method == "mining.subscribe":
                s.subscribed = True
            elif method == "mining.authorize":
                if not s.subscribed:
                    await self.reply(cw, rid, False, [24, "subscribe required before authorize", None]); continue
                if len(params) < 2:
                    await self.reply(cw, rid, False, [24, "worker and password required", None]); continue
                worker, secret = str(params[0]), str(params[1])
                if s.authorized and worker != s.worker:
                    self.logger.emit("worker_switch_rejected", peer_ip=s.peer_ip, worker=worker)
                    await self.reply(cw, rid, False, [24, "worker identity already bound", None]); continue
                if not self.auth.verify(worker, secret):
                    banned = self.guard.record_auth_failure(s.peer_ip)
                    self.logger.emit("ip_banned" if banned else "auth_failure", peer_ip=s.peer_ip, worker=worker)
                    await self.reply(cw, rid, False, [24, "authorization failed", None])
                    if banned: return
                    continue
                s.authorized, s.worker = True, worker; self.guard.clear_failures(s.peer_ip)
                self.logger.emit("auth_success", peer_ip=s.peer_ip, worker=worker)
                msg = {"id": rid, "method": method, "params": [worker, "edge-authenticated"]}
                line = (json.dumps(msg, separators=(",", ":")) + "\n").encode()
            elif method == "mining.submit":
                if not s.authorized:
                    await self.reply(cw, rid, False, [24, "unauthorized worker", None]); continue
                if not s.submit_bucket.consume() or not self.global_submit.consume():
                    self.logger.emit("submit_rate_limit", peer_ip=s.peer_ip, worker=s.worker)
                    await self.reply(cw, rid, False, [20, "submit rate limit", None]); continue
                submit_worker = str(params[0]) if params else ""
                if submit_worker != s.worker:
                    self.logger.emit("submit_identity_mismatch", peer_ip=s.peer_ip, worker=submit_worker)
                    await self.reply(cw, rid, False, [24, "worker mismatch", None]); continue
            elif not s.authorized:
                await self.reply(cw, rid, False, [24, "authorization required", None]); continue
            uw.write(line); await uw.drain()

    async def upstream_to_client(self, s: EdgeSession, ur: asyncio.StreamReader, cw: asyncio.StreamWriter) -> None:
        while True:
            try: line = await asyncio.wait_for(ur.readline(), timeout=self.policy.idle_timeout_seconds)
            except asyncio.TimeoutError:
                self.logger.emit("upstream_idle_timeout", peer_ip=s.peer_ip, worker=s.worker); return
            if not line: return
            if len(line) > max(self.policy.max_line_bytes * 4, 65536):
                self.logger.emit("upstream_protocol_violation", peer_ip=s.peer_ip, worker=s.worker, reason="line_too_large"); return
            cw.write(line); await cw.drain()

    async def handle_client(self, cr: asyncio.StreamReader, cw: asyncio.StreamWriter) -> None:
        peer = cw.get_extra_info("peername"); ip = str(peer[0]) if isinstance(peer, tuple) and peer else "unknown"
        admitted, reason = self.guard.admit(ip)
        if not admitted:
            self.logger.emit("connection_rejected", peer_ip=ip, reason=reason); cw.close(); await cw.wait_closed(); return
        s = EdgeSession(ip, TokenBucket(self.policy.message_rate_per_second, self.policy.message_burst), TokenBucket(self.policy.submit_rate_per_second, self.policy.submit_burst))
        uw = None; self.logger.emit("connection_open", peer_ip=ip)
        try:
            try:
                ur, uw = await asyncio.wait_for(asyncio.open_connection(self.upstream_host, self.upstream_port, limit=max(self.policy.max_line_bytes * 4, 65536)), timeout=self.policy.upstream_connect_timeout_seconds)
            except Exception as exc:
                self.logger.emit("upstream_connect_failure", peer_ip=ip, reason=type(exc).__name__); return
            a = asyncio.create_task(self.client_to_upstream(s, cr, cw, uw)); b = asyncio.create_task(self.upstream_to_client(s, ur, cw))
            done, pending = await asyncio.wait({a, b}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending: t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for t in done:
                if not t.cancelled() and t.exception(): self.logger.emit("session_error", peer_ip=ip, worker=s.worker, reason=type(t.exception()).__name__)
        finally:
            self.guard.release(ip)
            if uw:
                uw.close()
                try: await uw.wait_closed()
                except ConnectionError: pass
            cw.close()
            try: await cw.wait_closed()
            except ConnectionError: pass
            self.logger.emit("connection_close", peer_ip=ip, worker=s.worker)

    async def start(self) -> asyncio.AbstractServer:
        return await asyncio.start_server(self.handle_client, self.listen, self.port, ssl=self.tls_context,
            ssl_handshake_timeout=self.policy.tls_handshake_timeout_seconds if self.tls_context else None,
            limit=self.policy.max_line_bytes + 1, backlog=min(self.policy.max_connections, 1024))

    async def run(self) -> None:
        server = await self.start(); sockets = ", ".join(str(x.getsockname()) for x in server.sockets or [])
        print(f"crakpool-edge ready listen={sockets} transport={'tls' if self.tls_context else 'plaintext-loopback'} upstream={self.upstream_host}:{self.upstream_port}", flush=True)
        async with server: await server.serve_forever()


def command_credential(a: argparse.Namespace) -> int:
    p = SecurityPolicy.load(Path(a.policy).expanduser())
    secret = sys.stdin.readline().rstrip("\r\n") if a.secret_stdin else getpass.getpass("Worker secret: ")
    if not a.secret_stdin and secret != getpass.getpass("Confirm secret: "): raise ValueError("worker secrets did not match")
    write_worker_credential(Path(a.file).expanduser(), a.worker, secret, p); print(f"credential updated worker={a.worker} file={a.file}"); return 0


def build_runtime(a: argparse.Namespace) -> tuple[SecurityPolicy, WorkerAuth, ssl.SSLContext | None]:
    p = SecurityPolicy.load(Path(a.policy).expanduser()); auth = WorkerAuth(Path(a.auth_file).expanduser(), p)
    tls = build_tls_context(Path(a.tls_cert).expanduser() if a.tls_cert else None, Path(a.tls_key).expanduser() if a.tls_key else None)
    validate_serve_config(a.listen, a.upstream_host, tls, auth, p); return p, auth, tls


def command_check(a: argparse.Namespace) -> int:
    _, _, tls = build_runtime(a)
    print(f"CRAK-028 pool edge configuration: OK public={str(not is_loopback_host(a.listen)).lower()} tls={str(tls is not None).lower()} worker_auth=required upstream_loopback=required"); return 0


def command_serve(a: argparse.Namespace) -> int:
    p, auth, tls = build_runtime(a)
    g = EdgeGateway(p, auth, a.listen, a.port, a.upstream_host, a.upstream_port, tls, Path(a.security_log).expanduser() if a.security_log else None)
    try: asyncio.run(g.run())
    except KeyboardInterrupt: print("crakpool-edge stopped", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="CRAK-028 hardened Crakbit Stratum edge"); sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("credential"); c.add_argument("--policy", default=str(default_policy_path())); c.add_argument("--file", required=True); c.add_argument("--worker", required=True); c.add_argument("--secret-stdin", action="store_true"); c.set_defaults(func=command_credential)
    def common(x: argparse.ArgumentParser) -> None:
        x.add_argument("--policy", default=str(default_policy_path())); x.add_argument("--auth-file", required=True); x.add_argument("--listen", default="127.0.0.1"); x.add_argument("--port", type=int, default=3443); x.add_argument("--upstream-host", default="127.0.0.1"); x.add_argument("--upstream-port", type=int, default=3333); x.add_argument("--tls-cert"); x.add_argument("--tls-key")
    chk = sub.add_parser("check"); common(chk); chk.set_defaults(func=command_check)
    serve = sub.add_parser("serve"); common(serve); serve.add_argument("--security-log"); serve.set_defaults(func=command_serve)
    return ap


def main() -> int:
    a = build_parser().parse_args()
    if hasattr(a, "port") and not 1 <= a.port <= 65535: raise ValueError("--port must be 1..65535")
    if hasattr(a, "upstream_port") and not 1 <= a.upstream_port <= 65535: raise ValueError("--upstream-port must be 1..65535")
    return int(a.func(a))


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError, ssl.SSLError) as exc:
        print(f"crakpool-edge: {exc}", file=sys.stderr); raise SystemExit(1)
