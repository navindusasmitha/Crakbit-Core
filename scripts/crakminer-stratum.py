#!/usr/bin/env python3
"""Crakbit external Stratum worker with CRAK-028 TLS/auth support."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import ssl
import stat
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any

getcontext().prec = 90
DIFF1_TARGET = int("00000000ffff0000000000000000000000000000000000000000000000000000", 16)
MAX_TARGET = (1 << 256) - 1


def hash256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def difficulty_target(value: str | float) -> int:
    try:
        difficulty = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid share difficulty") from exc
    if not difficulty.is_finite() or difficulty <= 0:
        raise ValueError("share difficulty must be positive")
    return min(max(int(Decimal(DIFF1_TARGET) / difficulty), 1), MAX_TARGET)


def compact_target(bits: int) -> int:
    exponent = bits >> 24
    mantissa = bits & 0x007FFFFF
    if bits & 0x00800000:
        raise ValueError("negative compact target")
    target = mantissa >> (8 * (3 - exponent)) if exponent <= 3 else mantissa << (8 * (exponent - 3))
    if target <= 0 or target > MAX_TARGET:
        raise ValueError("compact target outside uint256 range")
    return target


def resolve_scanner(explicit: str | None) -> str:
    if explicit:
        return explicit
    here = Path(__file__).resolve().parent
    sibling = here / "crakminer-scan"
    if sibling.exists() and os.access(sibling, os.X_OK):
        return str(sibling)
    found = shutil.which("crakminer-scan")
    if found:
        return found
    raise SystemExit("crakminer-scan not found; use --scanner")


def private_file_permissions_ok(path: Path) -> bool:
    if os.name != "posix":
        return True
    return (stat.S_IMODE(path.stat().st_mode) & 0o077) == 0


def load_worker_secret(password: str | None, password_file: str | None, password_stdin: bool) -> str:
    selected = sum([password is not None, password_file is not None, password_stdin])
    if selected > 1:
        raise ValueError("choose only one of --password, --password-file, or --password-stdin")
    if password_file:
        path = Path(password_file).expanduser()
        if not path.is_file():
            raise ValueError(f"password file not found: {path}")
        if not private_file_permissions_ok(path):
            raise ValueError(f"password file must not be group/world-readable: {path}")
        text = path.read_text(encoding="utf-8")
        secret = text.splitlines()[0] if text else ""
    elif password_stdin:
        secret = sys.stdin.readline().rstrip("\r\n")
    elif password is not None:
        secret = password
    else:
        secret = "x"
    if not secret:
        raise ValueError("worker password must not be empty")
    if len(secret.encode("utf-8")) > 4096:
        raise ValueError("worker password is unreasonably large")
    return secret


def make_tls_context(ca_file: str | None) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=ca_file)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def open_pool_socket(
    host: str,
    port: int,
    *,
    use_tls: bool,
    tls_server_name: str | None,
    tls_ca_file: str | None,
    timeout: float = 10.0,
) -> socket.socket:
    raw = socket.create_connection((host, port), timeout=timeout)
    if not use_tls:
        raw.settimeout(None)
        return raw
    context = make_tls_context(tls_ca_file)
    server_name = tls_server_name or host
    try:
        wrapped = context.wrap_socket(raw, server_hostname=server_name)
    except Exception:
        raw.close()
        raise
    wrapped.settimeout(None)
    return wrapped


def parse_scan_result(text: str) -> tuple[int, str, int]:
    fields = dict(token.split("=", 1) for token in text.strip().split() if "=" in token)
    if not {"nonce", "hash", "attempts"} <= fields.keys():
        raise ValueError(f"unexpected scanner output: {text!r}")
    return int(fields["nonce"]), fields["hash"].lower(), int(fields["attempts"])


@dataclass(frozen=True)
class Job:
    job_id: str
    previous: str
    coinb1: bytes
    coinb2: bytes
    branch: tuple[bytes, ...]
    version: int
    bits: int
    ntime: int
    ntime_hex: str
    clean: bool


class Stratum:
    def __init__(
        self,
        host: str,
        port: int,
        worker: str,
        password: str,
        *,
        use_tls: bool = False,
        tls_server_name: str | None = None,
        tls_ca_file: str | None = None,
    ):
        self.host = host
        self.port = port
        self.worker = worker
        self.password = password
        self.use_tls = use_tls
        self.sock = open_pool_socket(
            host, port, use_tls=use_tls, tls_server_name=tls_server_name,
            tls_ca_file=tls_ca_file,
        )
        self.reader = self.sock.makefile("r", encoding="utf-8", newline="\n")
        self.writer = self.sock.makefile("w", encoding="utf-8", newline="\n")
        self.write_lock = threading.Lock()
        self.cv = threading.Condition()
        self.responses: dict[int, dict[str, Any]] = {}
        self.next_id = 1
        self.extranonce1 = b""
        self.extranonce2_size = 0
        self.share_difficulty: float = 1.0
        self.job: Job | None = None
        self.generation = 0
        self.closed = False
        self.reader_error: Exception | None = None
        self.thread = threading.Thread(target=self._reader_loop, name="crak-stratum-reader", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.reader.close()
            self.writer.close()
        finally:
            self.sock.close()

    def _send(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, separators=(",", ":"))
        with self.write_lock:
            self.writer.write(line + "\n")
            self.writer.flush()

    def request(self, method: str, params: list[Any], timeout: float = 10.0) -> Any:
        with self.cv:
            request_id = self.next_id
            self.next_id += 1
        self._send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        with self.cv:
            while request_id not in self.responses:
                if self.reader_error:
                    raise RuntimeError(f"Stratum reader failed: {self.reader_error}")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Stratum request timed out: {method}")
                self.cv.wait(remaining)
            response = self.responses.pop(request_id)
        if response.get("error") is not None:
            raise RuntimeError(f"Stratum {method} error: {response['error']}")
        return response.get("result")

    def _reader_loop(self) -> None:
        try:
            for line in self.reader:
                message = json.loads(line)
                if message.get("id") is not None:
                    with self.cv:
                        self.responses[int(message["id"])] = message
                        self.cv.notify_all()
                    continue
                method = message.get("method")
                params = message.get("params", [])
                if method == "mining.set_difficulty" and params:
                    with self.cv:
                        self.share_difficulty = float(params[0])
                        self.cv.notify_all()
                elif method == "mining.notify":
                    if len(params) != 9:
                        raise ValueError("mining.notify expected 9 params")
                    job = Job(
                        job_id=str(params[0]), previous=str(params[1]),
                        coinb1=bytes.fromhex(str(params[2])), coinb2=bytes.fromhex(str(params[3])),
                        branch=tuple(bytes.fromhex(str(item)) for item in params[4]),
                        version=int(str(params[5]), 16), bits=int(str(params[6]), 16),
                        ntime=int(str(params[7]), 16), ntime_hex=str(params[7]), clean=bool(params[8]),
                    )
                    with self.cv:
                        self.job = job
                        self.generation += 1
                        self.cv.notify_all()
        except Exception as exc:
            if not self.closed:
                self.reader_error = exc
                with self.cv:
                    self.cv.notify_all()

    def start(self) -> None:
        result = self.request("mining.subscribe", ["crakminer-stratum/0.1"])
        if not isinstance(result, list) or len(result) != 3:
            raise RuntimeError(f"unexpected mining.subscribe result: {result!r}")
        self.extranonce1 = bytes.fromhex(str(result[1]))
        self.extranonce2_size = int(result[2])
        if not 1 <= self.extranonce2_size <= 16:
            raise RuntimeError("invalid extranonce2 size from pool")
        authorized = self.request("mining.authorize", [self.worker, self.password])
        if authorized is not True:
            raise RuntimeError("worker authorization rejected")

    def snapshot_job(self) -> tuple[Job, int, float]:
        with self.cv:
            while self.job is None:
                if self.reader_error:
                    raise RuntimeError(f"Stratum reader failed: {self.reader_error}")
                self.cv.wait(1.0)
            return self.job, self.generation, self.share_difficulty

    def is_current(self, generation: int, job_id: str) -> bool:
        with self.cv:
            return self.generation == generation and self.job is not None and self.job.job_id == job_id


def build_header(job: Job, extranonce1: bytes, extranonce2: bytes) -> bytes:
    coinbase = job.coinb1 + extranonce1 + extranonce2 + job.coinb2
    merkle = hash256(coinbase)
    for sibling in job.branch:
        merkle = hash256(merkle + sibling)
    header = (
        struct.pack("<I", job.version) + bytes.fromhex(job.previous)[::-1] + merkle
        + struct.pack("<I", job.ntime) + struct.pack("<I", job.bits) + struct.pack("<I", 0)
    )
    if len(header) != 80:
        raise AssertionError("header is not 80 bytes")
    return header


def scan(scanner: str, header: bytes, target: int, threads: int, cpu_limit: int, batch_hashes: int) -> tuple[int, str, int] | None:
    cmd = [scanner, "--header", header.hex(), "--target", f"{target:064x}", "--threads", str(threads),
           "--cpu-limit", str(cpu_limit), "--max-hashes", str(batch_hashes)]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode == 2:
        return None
    if proc.returncode != 0:
        raise RuntimeError(f"native scanner failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return parse_scan_result(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit Stratum CPU worker")
    parser.add_argument("--pool", required=True, help="host:port")
    parser.add_argument("--worker", required=True)
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument("--password", help="worker password; avoid on shared systems because argv may be visible")
    auth.add_argument("--password-file", help="private mode-0600 file whose first line is the worker password")
    auth.add_argument("--password-stdin", action="store_true", help="read worker password from one stdin line")
    parser.add_argument("--tls", action="store_true", help="use verified TLS for Stratum transport")
    parser.add_argument("--tls-server-name", help="TLS certificate hostname; defaults to pool host")
    parser.add_argument("--tls-ca-file", help="optional CA bundle/self-signed CA for pool TLS verification")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--cpu-limit", type=int, default=100)
    parser.add_argument("--batch-hashes", type=int, default=250000)
    parser.add_argument("--shares", type=int, default=0, help="stop after accepted shares; 0 = unlimited")
    parser.add_argument("--blocks", type=int, default=0, help="stop after accepted network-target blocks; 0 = unlimited")
    parser.add_argument("--scanner")
    args = parser.parse_args()

    if ":" not in args.pool:
        parser.error("--pool must be host:port")
    host, port_text = args.pool.rsplit(":", 1)
    try:
        port = int(port_text)
    except ValueError:
        parser.error("pool port must be an integer")
    if not 1 <= port <= 65535:
        parser.error("pool port must be 1..65535")
    if not 1 <= args.threads <= 256:
        parser.error("--threads must be 1..256")
    if not 1 <= args.cpu_limit <= 100:
        parser.error("--cpu-limit must be 1..100")
    if args.batch_hashes < 1 or args.shares < 0 or args.blocks < 0:
        parser.error("batch/shares/blocks values are invalid")
    if (args.tls_server_name or args.tls_ca_file) and not args.tls:
        parser.error("--tls-server-name/--tls-ca-file require --tls")

    try:
        secret = load_worker_secret(args.password, args.password_file, args.password_stdin)
    except ValueError as exc:
        parser.error(str(exc))
    scanner = resolve_scanner(args.scanner)
    client = Stratum(
        host, port, args.worker, secret, use_tls=args.tls,
        tls_server_name=args.tls_server_name, tls_ca_file=args.tls_ca_file,
    )
    secret = ""
    accepted = blocks = extranonce_counter = total_hashes = 0
    started_all = time.monotonic()

    try:
        client.start()
        print(
            f"crakminer-stratum connected pool={args.pool} worker={args.worker} tls={str(args.tls).lower()} "
            f"threads={args.threads} cpu_limit={args.cpu_limit}% extranonce1={client.extranonce1.hex()}",
            flush=True,
        )
        while True:
            if args.shares and accepted >= args.shares:
                break
            if args.blocks and blocks >= args.blocks:
                break
            job, generation, difficulty = client.snapshot_job()
            target = difficulty_target(difficulty)
            network_target = compact_target(job.bits)
            extranonce_counter = (extranonce_counter + 1) % (1 << (8 * client.extranonce2_size))
            extranonce2 = extranonce_counter.to_bytes(client.extranonce2_size, "big")
            header = build_header(job, client.extranonce1, extranonce2)
            started = time.monotonic()
            result = scan(scanner, header, target, args.threads, args.cpu_limit, args.batch_hashes)
            elapsed = max(time.monotonic() - started, 1e-9)
            if result is None:
                total_hashes += args.batch_hashes
                print(f"crakminer-stratum work job={job.job_id} no-share rate={args.batch_hashes / elapsed:.2f} H/s", flush=True)
                continue
            nonce, block_hash, attempts = result
            total_hashes += attempts
            if not client.is_current(generation, job.job_id):
                print(f"crakminer-stratum stale-local job={job.job_id} hash={block_hash}", file=sys.stderr, flush=True)
                continue
            try:
                ok = client.request("mining.submit", [args.worker, job.job_id, extranonce2.hex(), job.ntime_hex, f"{nonce:08x}"], timeout=20.0)
            except RuntimeError as exc:
                print(f"crakminer-stratum share-rejected job={job.job_id} reason={exc}", file=sys.stderr, flush=True)
                continue
            if ok is not True:
                print(f"crakminer-stratum share-rejected job={job.job_id}", file=sys.stderr, flush=True)
                continue
            accepted += 1
            if int(block_hash, 16) <= network_target:
                blocks += 1
                print(f"crakminer-stratum BLOCK blocks={blocks} hash={block_hash} height-job={job.job_id}", flush=True)
            print(
                f"crakminer-stratum accepted={accepted} job={job.job_id} nonce={nonce} hash={block_hash} "
                f"attempts={attempts} rate={attempts / elapsed:.2f} H/s", flush=True,
            )

        elapsed_all = max(time.monotonic() - started_all, 1e-9)
        print(
            f"crakminer-stratum complete accepted={accepted} blocks={blocks} hashes={total_hashes} "
            f"avg_rate={total_hashes / elapsed_all:.2f} H/s", flush=True,
        )
        return 0
    except KeyboardInterrupt:
        print("crakminer-stratum stopped", file=sys.stderr)
        return 130
    finally:
        client.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, TimeoutError, ssl.SSLError) as exc:
        print(f"crakminer-stratum: {exc}", file=sys.stderr)
        raise SystemExit(1)
