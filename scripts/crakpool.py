#!/usr/bin/env python3
"""CRAK-014 Crakbit Stratum V1 subset pool server.

The pool keeps crakbitd RPC private, distributes getblocktemplate work over a
JSON-lines Stratum TCP socket, validates yespower shares with crakminer-scan,
and submits full blocks back to the node. This first pool milestone pays the
whole coinbase to one configured pool address; worker payout accounting is not
implemented yet.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any

getcontext().prec = 90
DIFF1_TARGET = int("00000000ffff0000000000000000000000000000000000000000000000000000", 16)
MAX_TARGET = (1 << 256) - 1


def hash256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative varint")
    if value < 0xFD:
        return bytes([value])
    if value <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", value)
    if value <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", value)
    return b"\xff" + struct.pack("<Q", value)


def scriptnum(value: int) -> bytes:
    if value == 0:
        return b""
    if value < 0:
        raise ValueError("negative script number")
    out = bytearray()
    while value:
        out.append(value & 0xFF)
        value >>= 8
    if out[-1] & 0x80:
        out.append(0)
    return bytes(out)


def push_data(data: bytes) -> bytes:
    size = len(data)
    if size < 0x4C:
        return bytes([size]) + data
    if size <= 0xFF:
        return b"\x4c" + bytes([size]) + data
    if size <= 0xFFFF:
        return b"\x4d" + struct.pack("<H", size) + data
    raise ValueError("push_data too large")


def bip34_height_prefix(height: int) -> bytes:
    if height < 0:
        raise ValueError("negative height")
    if height == 0:
        return b"\x00"
    if 1 <= height <= 16:
        return bytes([0x50 + height])
    return push_data(scriptnum(height))


def difficulty_target(value: str) -> int:
    try:
        difficulty = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid share difficulty") from exc
    if not difficulty.is_finite() or difficulty <= 0:
        raise ValueError("share difficulty must be positive")
    target = int(Decimal(DIFF1_TARGET) / difficulty)
    return min(max(target, 1), MAX_TARGET)


def merkle_branch_for_coinbase(template: dict[str, Any]) -> list[bytes]:
    """Return internal-byte-order sibling hashes for coinbase index zero."""
    level: list[bytes | None] = [None]
    for tx in template.get("transactions", []):
        level.append(bytes.fromhex(tx["txid"])[::-1])
    branch: list[bytes] = []
    while len(level) > 1:
        if len(level) & 1:
            level.append(level[-1])
        sibling = level[1]
        if sibling is None:
            raise ValueError("invalid merkle tree sibling")
        branch.append(sibling)
        nxt: list[bytes | None] = []
        for i in range(0, len(level), 2):
            left, right = level[i], level[i + 1]
            if left is None or right is None:
                nxt.append(None)
            else:
                nxt.append(hash256(left + right))
        level = nxt
    return branch


def merkle_from_coinbase(coinbase_txid_internal: bytes, branch: list[bytes]) -> bytes:
    root = coinbase_txid_internal
    for sibling in branch:
        root = hash256(root + sibling)
    return root


def resolve_executable(explicit: str | None, sibling: str, path_name: str) -> str:
    if explicit:
        return explicit
    here = Path(__file__).resolve().parent
    candidate = here / sibling
    if candidate.exists() and os.access(candidate, os.X_OK):
        return str(candidate)
    found = shutil.which(path_name)
    if found:
        return found
    raise SystemExit(f"{path_name} not found; use the explicit path option")


class Rpc:
    def __init__(self, cli: str, network: str, datadir: str, rpcport: int | None):
        self.base = [cli, "-testnet4" if network == "testnet4" else "-regtest", f"-datadir={datadir}"]
        if rpcport is not None:
            self.base.append(f"-rpcport={rpcport}")

    def call(self, method: str, *params: str, wallet: str | None = None, parse_json: bool = True):
        cmd = self.base[:]
        if wallet:
            cmd.append(f"-rpcwallet={wallet}")
        cmd.extend([method, *params])
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise RuntimeError(f"RPC {method} failed: {proc.stderr.strip() or proc.stdout.strip()}")
        text = proc.stdout.strip()
        if not parse_json:
            return text
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


@dataclass
class Job:
    job_id: str
    template: dict[str, Any]
    coinb1: bytes
    coinb2: bytes
    branch: list[bytes]
    witness: bool
    network_target: int
    created: float = field(default_factory=time.monotonic)

    @property
    def ntime_hex(self) -> str:
        return f"{int(self.template['curtime']):08x}"

    @property
    def version_hex(self) -> str:
        return f"{int(self.template['version']) & 0xffffffff:08x}"


@dataclass(eq=False)
class Session:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    extranonce1: bytes
    subscribed: bool = False
    authorized: bool = False
    worker: str = ""
    seen: set[tuple[str, str, str, str]] = field(default_factory=set)


class Pool:
    def __init__(
        self,
        rpc: Rpc,
        scanner: str,
        payout_script: bytes,
        listen: str,
        port: int,
        share_difficulty: str,
        extranonce1_size: int = 4,
        extranonce2_size: int = 4,
        refresh_seconds: float = 2.0,
    ):
        self.rpc = rpc
        self.scanner = scanner
        self.payout_script = payout_script
        self.listen = listen
        self.port = port
        self.share_difficulty = share_difficulty
        self.share_target = difficulty_target(share_difficulty)
        self.extranonce1_size = extranonce1_size
        self.extranonce2_size = extranonce2_size
        self.refresh_seconds = refresh_seconds
        self.sessions: set[Session] = set()
        self.jobs: dict[str, Job] = {}
        self.current_job: Job | None = None
        self.job_counter = 0
        self.accepted_shares = 0
        self.rejected_shares = 0
        self.blocks_found = 0
        self.last_tip = ""

    def make_coinbase_parts(self, template: dict[str, Any]) -> tuple[bytes, bytes, bool]:
        height = int(template["height"])
        flags_hex = template.get("coinbaseaux", {}).get("flags", "")
        flags = bytes.fromhex(flags_hex) if flags_hex else b""
        script_prefix = bip34_height_prefix(height) + flags + b"/CRAK/"
        script_len = len(script_prefix) + self.extranonce1_size + self.extranonce2_size
        if not 2 <= script_len <= 100:
            raise ValueError(f"coinbase scriptSig length {script_len} outside 2..100")

        version = struct.pack("<I", 2)
        coinb1 = (
            version
            + varint(1)
            + (b"\x00" * 32)
            + struct.pack("<I", 0xFFFFFFFF)
            + varint(script_len)
            + script_prefix
        )

        outputs: list[bytes] = []
        reward = int(template["coinbasevalue"])
        outputs.append(struct.pack("<Q", reward) + varint(len(self.payout_script)) + self.payout_script)
        commitment_hex = template.get("default_witness_commitment")
        commitment = bytes.fromhex(commitment_hex) if commitment_hex else b""
        if commitment:
            outputs.append(struct.pack("<Q", 0) + varint(len(commitment)) + commitment)

        coinb2 = (
            struct.pack("<I", 0xFFFFFFFF)
            + varint(len(outputs))
            + b"".join(outputs)
            + struct.pack("<I", 0)
        )
        return coinb1, coinb2, bool(commitment)

    def build_job(self, template: dict[str, Any]) -> Job:
        self.job_counter += 1
        coinb1, coinb2, witness = self.make_coinbase_parts(template)
        branch = merkle_branch_for_coinbase(template)
        network_target = int(template["target"], 16)
        job_id = f"{int(template['height']):x}-{self.job_counter:x}"
        return Job(job_id, template, coinb1, coinb2, branch, witness, network_target)

    def build_coinbase(self, job: Job, extranonce1: bytes, extranonce2: bytes) -> tuple[bytes, bytes]:
        stripped = job.coinb1 + extranonce1 + extranonce2 + job.coinb2
        txid_internal = hash256(stripped)
        if not job.witness:
            return stripped, txid_internal
        # Insert SegWit marker/flag after version and the reserved-value witness
        # immediately before nLockTime. The stripped transaction remains the txid.
        full = stripped[:4] + b"\x00\x01" + stripped[4:-4] + varint(1) + varint(32) + (b"\x00" * 32) + stripped[-4:]
        return full, txid_internal

    def build_header(self, job: Job, merkle: bytes, ntime: int, nonce: int) -> bytes:
        version = int(job.template["version"])
        previous = bytes.fromhex(job.template["previousblockhash"])[::-1]
        bits = int(job.template["bits"], 16)
        header = (
            struct.pack("<i", version)
            + previous
            + merkle
            + struct.pack("<I", ntime)
            + struct.pack("<I", bits)
            + struct.pack("<I", nonce)
        )
        if len(header) != 80:
            raise AssertionError("header is not 80 bytes")
        return header

    async def rpc_async(self, method: str, *params: str, wallet: str | None = None, parse_json: bool = True):
        return await asyncio.to_thread(self.rpc.call, method, *params, wallet=wallet, parse_json=parse_json)

    async def scanner_hash(self, header: bytes, nonce: int) -> str | None:
        cmd = [
            self.scanner,
            "--header", header.hex(),
            "--target", f"{self.share_target:064x}",
            "--start-nonce", str(nonce),
            "--max-hashes", "1",
            "--threads", "1",
            "--cpu-limit", "100",
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        text = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode == 2:
            return None
        if proc.returncode != 0:
            raise RuntimeError(f"scanner failed: {stderr.decode('utf-8', errors='replace').strip() or text}")
        fields = dict(token.split("=", 1) for token in text.split() if "=" in token)
        block_hash = fields.get("hash")
        if not block_hash or len(block_hash) != 64:
            raise RuntimeError(f"unexpected scanner output: {text}")
        return block_hash.lower()

    async def send(self, session: Session, payload: dict[str, Any]) -> None:
        session.writer.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
        await session.writer.drain()

    async def reply(self, session: Session, request_id: Any, result: Any = None, error: Any = None) -> None:
        await self.send(session, {"id": request_id, "result": result, "error": error})

    async def notify(self, session: Session, clean: bool = True) -> None:
        job = self.current_job
        if not job or not session.subscribed:
            return
        await self.send(session, {
            "id": None,
            "method": "mining.notify",
            "params": [
                job.job_id,
                job.template["previousblockhash"],
                job.coinb1.hex(),
                job.coinb2.hex(),
                [item.hex() for item in job.branch],
                job.version_hex,
                job.template["bits"],
                job.ntime_hex,
                clean,
            ],
        })

    async def set_difficulty(self, session: Session) -> None:
        await self.send(session, {"id": None, "method": "mining.set_difficulty", "params": [float(Decimal(self.share_difficulty))]})

    async def broadcast_job(self, clean: bool = True) -> None:
        dead: list[Session] = []
        for session in list(self.sessions):
            if not session.authorized:
                continue
            try:
                await self.notify(session, clean)
            except (ConnectionError, BrokenPipeError):
                dead.append(session)
        for session in dead:
            self.sessions.discard(session)

    async def refresh_template(self, force: bool = False) -> None:
        template = await self.rpc_async("getblocktemplate", json.dumps({"rules": ["segwit"]}, separators=(",", ":")))
        if not isinstance(template, dict):
            raise RuntimeError("getblocktemplate did not return an object")
        tip = str(template["previousblockhash"])
        if not force and self.current_job and tip == self.last_tip:
            return
        job = self.build_job(template)
        self.jobs[job.job_id] = job
        self.current_job = job
        self.last_tip = tip
        # Keep a small stale-job window for explicit stale-share errors.
        if len(self.jobs) > 32:
            for old_id in list(self.jobs)[:-32]:
                self.jobs.pop(old_id, None)
        print(f"crakpool job={job.job_id} height={template['height']} tip={tip} txs={len(template.get('transactions', []))}", flush=True)
        await self.broadcast_job(clean=True)

    async def template_loop(self) -> None:
        while True:
            try:
                await self.refresh_template()
            except Exception as exc:
                print(f"crakpool template error: {exc}", file=sys.stderr, flush=True)
            await asyncio.sleep(self.refresh_seconds)

    async def handle_submit(self, session: Session, request_id: Any, params: list[Any]) -> None:
        if not session.authorized:
            await self.reply(session, request_id, False, [24, "unauthorized worker", None])
            return
        if len(params) != 5:
            await self.reply(session, request_id, False, [20, "mining.submit expects 5 params", None])
            return
        worker, job_id, extranonce2_hex, ntime_hex, nonce_hex = map(str, params)
        job = self.jobs.get(job_id)
        if job is None or self.current_job is None or job_id != self.current_job.job_id:
            self.rejected_shares += 1
            await self.reply(session, request_id, False, [21, "stale job", None])
            return
        try:
            extranonce2 = bytes.fromhex(extranonce2_hex)
            if len(extranonce2) != self.extranonce2_size:
                raise ValueError("wrong extranonce2 size")
            if len(ntime_hex) != 8 or len(nonce_hex) != 8:
                raise ValueError("ntime/nonce must be 4-byte hex")
            ntime = int(ntime_hex, 16)
            nonce = int(nonce_hex, 16)
        except (ValueError, TypeError) as exc:
            self.rejected_shares += 1
            await self.reply(session, request_id, False, [20, str(exc), None])
            return
        if ntime != int(job.template["curtime"]):
            self.rejected_shares += 1
            await self.reply(session, request_id, False, [20, "ntime rolling not enabled in CRAK-014", None])
            return

        share_key = (job_id, extranonce2_hex.lower(), ntime_hex.lower(), nonce_hex.lower())
        if share_key in session.seen:
            self.rejected_shares += 1
            await self.reply(session, request_id, False, [22, "duplicate share", None])
            return
        session.seen.add(share_key)

        full_coinbase, coinbase_txid = self.build_coinbase(job, session.extranonce1, extranonce2)
        merkle = merkle_from_coinbase(coinbase_txid, job.branch)
        header = self.build_header(job, merkle, ntime, nonce)
        block_hash = await self.scanner_hash(header, nonce)
        if block_hash is None:
            self.rejected_shares += 1
            await self.reply(session, request_id, False, [23, "low difficulty share", None])
            return

        self.accepted_shares += 1
        is_block = int(block_hash, 16) <= job.network_target
        if is_block:
            tx_data = [bytes.fromhex(tx["data"]) for tx in job.template.get("transactions", [])]
            block = header + varint(1 + len(tx_data)) + full_coinbase + b"".join(tx_data)
            submit = await self.rpc_async("submitblock", block.hex())
            if submit not in (None, "", "duplicate"):
                self.rejected_shares += 1
                await self.reply(session, request_id, False, [20, f"block rejected: {submit}", None])
                return
            self.blocks_found += 1
            print(
                f"crakpool BLOCK worker={worker} hash={block_hash} height={job.template['height']} "
                f"shares={self.accepted_shares}",
                flush=True,
            )
            await self.reply(session, request_id, True, None)
            await self.refresh_template(force=True)
            return

        print(f"crakpool share worker={worker} hash={block_hash} accepted={self.accepted_shares}", flush=True)
        await self.reply(session, request_id, True, None)

    async def handle_message(self, session: Session, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params", [])
        if method == "mining.subscribe":
            session.subscribed = True
            subscriptions = [["mining.set_difficulty", "crakbit-diff"], ["mining.notify", "crakbit-job"]]
            await self.reply(session, request_id, [subscriptions, session.extranonce1.hex(), self.extranonce2_size], None)
            await self.set_difficulty(session)
            return
        if method == "mining.authorize":
            worker = str(params[0]) if params else ""
            if not worker or len(worker) > 128:
                await self.reply(session, request_id, False, [24, "invalid worker name", None])
                return
            session.worker = worker
            session.authorized = True
            await self.reply(session, request_id, True, None)
            await self.notify(session, clean=True)
            return
        if method == "mining.submit":
            await self.handle_submit(session, request_id, list(params))
            return
        if method in ("mining.extranonce.subscribe", "mining.suggest_difficulty"):
            await self.reply(session, request_id, True, None)
            return
        await self.reply(session, request_id, None, [20, f"unsupported method: {method}", None])

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        session = Session(reader, writer, secrets.token_bytes(self.extranonce1_size))
        self.sessions.add(session)
        print(f"crakpool connect peer={peer} extranonce1={session.extranonce1.hex()}", flush=True)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                if len(line) > 65536:
                    raise ValueError("Stratum line too large")
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("request is not an object")
                    await self.handle_message(session, message)
                except json.JSONDecodeError:
                    await self.reply(session, None, None, [20, "invalid JSON", None])
        except (ConnectionError, asyncio.CancelledError):
            pass
        except Exception as exc:
            print(f"crakpool client error peer={peer}: {exc}", file=sys.stderr, flush=True)
        finally:
            self.sessions.discard(session)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            print(f"crakpool disconnect peer={peer}", flush=True)

    async def run(self) -> None:
        await self.refresh_template(force=True)
        server = await asyncio.start_server(self.handle_client, self.listen, self.port, limit=65536)
        sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
        print(
            f"crakpool ready listen={sockets} share_difficulty={self.share_difficulty} "
            f"share_target={self.share_target:064x}",
            flush=True,
        )
        refresher = asyncio.create_task(self.template_loop())
        try:
            async with server:
                await server.serve_forever()
        finally:
            refresher.cancel()
            await asyncio.gather(refresher, return_exceptions=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit CRAK-014 Stratum V1 subset pool")
    parser.add_argument("--network", choices=["testnet4", "regtest"], default="testnet4")
    payout = parser.add_mutually_exclusive_group(required=True)
    payout.add_argument("--wallet", help="wallet used once at startup to obtain the pool payout address")
    payout.add_argument("--address", help="fixed pool payout address")
    parser.add_argument("--listen", default="127.0.0.1", help="Stratum bind address (default: localhost)")
    parser.add_argument("--port", type=int, default=3333)
    parser.add_argument("--share-difficulty", default="0.0001")
    parser.add_argument("--datadir", default=os.environ.get("CRAKBIT_DATADIR", str(Path.home() / ".crakbit")))
    parser.add_argument("--rpcport", type=int)
    parser.add_argument("--cli")
    parser.add_argument("--scanner")
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1..65535")
    difficulty_target(args.share_difficulty)

    cli = resolve_executable(args.cli, "crakbit-cli", "crakbit-cli")
    scanner = resolve_executable(args.scanner, "crakminer-scan", "crakminer-scan")
    rpc = Rpc(cli, args.network, args.datadir, args.rpcport)
    rpc.call("getblockcount")
    address = args.address
    if args.wallet:
        address = rpc.call("getnewaddress", "", "bech32", wallet=args.wallet, parse_json=False)
    assert address
    info = rpc.call("validateaddress", address)
    if not isinstance(info, dict) or not info.get("isvalid") or not info.get("scriptPubKey"):
        raise SystemExit(f"invalid pool payout address for {args.network}: {address}")
    payout_script = bytes.fromhex(info["scriptPubKey"])

    pool = Pool(rpc, scanner, payout_script, args.listen, args.port, args.share_difficulty)
    print(f"crakpool payout={address} network={args.network}", flush=True)
    try:
        asyncio.run(pool.run())
    except KeyboardInterrupt:
        print("crakpool stopped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"crakpool: {exc}", file=sys.stderr)
        raise SystemExit(1)
