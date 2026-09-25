#!/usr/bin/env python3
"""CRAK-015 Crakbit pool accounting + vardiff layer.

This wraps the CRAK-014 Stratum server without changing consensus. Accepted
shares, found blocks and reward credits are persisted in SQLite. Reward credits
are accounting entries only: CRAK-015 does not create or broadcast payout
transactions.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
import sqlite3
import struct
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any

getcontext().prec = 90
HASHES_PER_DIFF1 = Decimal(2**32)


def load_base_pool():
    here = Path(__file__).resolve().parent
    for candidate in (here / "crakpool.py", here / "crakpool-base.py"):
        if not candidate.exists():
            continue
        spec = importlib.util.spec_from_file_location("crakpool_base", candidate)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    raise RuntimeError("CRAK-014 base pool module not found beside crakpool-accounting")


BASE = load_base_pool()


def as_decimal(value: str | int | float | Decimal) -> Decimal:
    try:
        out = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value: {value}") from exc
    if not out.is_finite():
        raise ValueError("decimal value must be finite")
    return out


def fmt_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text if text != "-0" else "0"


def allocate_satoshis(scores: dict[str, Decimal], total_sats: int) -> dict[str, int]:
    """Allocate every satoshi deterministically using largest remainders."""
    if total_sats < 0:
        raise ValueError("negative payout total")
    positive = {worker: score for worker, score in scores.items() if score > 0}
    if not positive or total_sats == 0:
        return {worker: 0 for worker in positive}
    score_total = sum(positive.values(), Decimal(0))
    floors: dict[str, int] = {}
    fractions: list[tuple[Decimal, str]] = []
    allocated = 0
    for worker in sorted(positive):
        exact = Decimal(total_sats) * positive[worker] / score_total
        whole = int(exact)
        floors[worker] = whole
        allocated += whole
        fractions.append((exact - whole, worker))
    remainder = total_sats - allocated
    fractions.sort(key=lambda item: (-item[0], item[1]))
    for _, worker in fractions[:remainder]:
        floors[worker] += 1
    if sum(floors.values()) != total_sats:
        raise AssertionError("payout allocator did not conserve satoshis")
    return floors


def next_vardiff(
    current: Decimal,
    observed_interval: float,
    target_interval: float,
    minimum: Decimal,
    maximum: Decimal,
    hysteresis: float = 0.25,
) -> Decimal:
    """Return the next share difficulty from an observed inter-share interval."""
    if observed_interval <= 0 or target_interval <= 0:
        return current
    lower = target_interval * (1.0 - hysteresis)
    upper = target_interval * (1.0 + hysteresis)
    if lower <= observed_interval <= upper:
        return current
    factor = target_interval / observed_interval
    factor = min(4.0, max(0.25, factor))
    updated = current * Decimal(str(factor))
    updated = min(max(updated, minimum), maximum)
    # Twelve significant decimal places is enough for Stratum difficulty while
    # keeping stable textual values in SQLite / protocol messages.
    if updated != 0:
        exponent = updated.adjusted() - 11
        quantum = Decimal(1).scaleb(exponent)
        updated = updated.quantize(quantum)
    return updated


class PoolLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS workers (
                worker TEXT PRIMARY KEY,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                current_difficulty TEXT NOT NULL,
                accepted_shares INTEGER NOT NULL DEFAULT 0,
                rejected_shares INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                worker TEXT NOT NULL,
                job_id TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                hash TEXT NOT NULL,
                is_block INTEGER NOT NULL,
                FOREIGN KEY(worker) REFERENCES workers(worker)
            );
            CREATE INDEX IF NOT EXISTS shares_worker_ts ON shares(worker, ts);
            CREATE INDEX IF NOT EXISTS shares_ts ON shares(ts);
            CREATE TABLE IF NOT EXISTS blocks (
                hash TEXT PRIMARY KEY,
                height INTEGER NOT NULL,
                ts REAL NOT NULL,
                reward_sats INTEGER NOT NULL,
                fee_sats INTEGER NOT NULL,
                distributable_sats INTEGER NOT NULL,
                payout_mode TEXT NOT NULL,
                start_share_id INTEGER NOT NULL,
                end_share_id INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS blocks_height ON blocks(height);
            CREATE TABLE IF NOT EXISTS credits (
                block_hash TEXT NOT NULL,
                worker TEXT NOT NULL,
                score TEXT NOT NULL,
                amount_sats INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                PRIMARY KEY(block_hash, worker),
                FOREIGN KEY(block_hash) REFERENCES blocks(hash),
                FOREIGN KEY(worker) REFERENCES workers(worker)
            );
            CREATE INDEX IF NOT EXISTS credits_worker_status ON credits(worker, status);
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def register_worker(self, worker: str, difficulty: Decimal) -> Decimal:
        now = time.time()
        row = self.db.execute("SELECT current_difficulty FROM workers WHERE worker=?", (worker,)).fetchone()
        if row is None:
            self.db.execute(
                "INSERT INTO workers(worker, first_seen, last_seen, current_difficulty) VALUES(?,?,?,?)",
                (worker, now, now, fmt_decimal(difficulty)),
            )
            self.db.commit()
            return difficulty
        self.db.execute("UPDATE workers SET last_seen=? WHERE worker=?", (now, worker))
        self.db.commit()
        try:
            saved = as_decimal(row["current_difficulty"])
        except ValueError:
            saved = difficulty
        return saved

    def set_worker_difficulty(self, worker: str, difficulty: Decimal) -> None:
        self.db.execute(
            "UPDATE workers SET current_difficulty=?, last_seen=? WHERE worker=?",
            (fmt_decimal(difficulty), time.time(), worker),
        )
        self.db.commit()

    def record_rejected(self, worker: str) -> None:
        if not worker:
            return
        self.db.execute(
            "UPDATE workers SET rejected_shares=rejected_shares+1, last_seen=? WHERE worker=?",
            (time.time(), worker),
        )
        self.db.commit()

    def record_share(self, worker: str, job_id: str, difficulty: Decimal, block_hash: str, is_block: bool) -> int:
        now = time.time()
        cur = self.db.execute(
            "INSERT INTO shares(ts, worker, job_id, difficulty, hash, is_block) VALUES(?,?,?,?,?,?)",
            (now, worker, job_id, fmt_decimal(difficulty), block_hash, 1 if is_block else 0),
        )
        self.db.execute(
            "UPDATE workers SET accepted_shares=accepted_shares+1, last_seen=? WHERE worker=?",
            (now, worker),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def _score_rows(self, rows: list[sqlite3.Row]) -> dict[str, Decimal]:
        scores: dict[str, Decimal] = {}
        for row in rows:
            worker = str(row["worker"])
            scores[worker] = scores.get(worker, Decimal(0)) + as_decimal(row["difficulty"])
        return scores

    def _payout_rows(self, mode: str, end_share_id: int, pplns_shares: int) -> tuple[int, list[sqlite3.Row]]:
        if mode == "proportional":
            previous = self.db.execute("SELECT COALESCE(MAX(end_share_id), 0) AS value FROM blocks").fetchone()
            start = int(previous["value"]) + 1
            rows = self.db.execute(
                "SELECT id, worker, difficulty FROM shares WHERE id BETWEEN ? AND ? ORDER BY id",
                (start, end_share_id),
            ).fetchall()
            return start, rows
        if mode == "pplns":
            rows = self.db.execute(
                "SELECT id, worker, difficulty FROM shares WHERE id<=? ORDER BY id DESC LIMIT ?",
                (end_share_id, pplns_shares),
            ).fetchall()
            if not rows:
                return end_share_id, []
            start = min(int(row["id"]) for row in rows)
            return start, rows
        raise ValueError(f"unknown payout mode: {mode}")

    def record_block_and_allocate(
        self,
        block_hash: str,
        height: int,
        reward_sats: int,
        end_share_id: int,
        mode: str,
        pplns_shares: int,
        pool_fee_bps: int,
    ) -> dict[str, int]:
        existing = self.db.execute("SELECT hash FROM blocks WHERE hash=?", (block_hash,)).fetchone()
        if existing is not None:
            rows = self.db.execute("SELECT worker, amount_sats FROM credits WHERE block_hash=?", (block_hash,)).fetchall()
            return {str(row["worker"]): int(row["amount_sats"]) for row in rows}
        start_share_id, rows = self._payout_rows(mode, end_share_id, pplns_shares)
        scores = self._score_rows(rows)
        if not scores:
            raise RuntimeError("cannot allocate block reward without credited shares")
        fee_sats = reward_sats * pool_fee_bps // 10000
        distributable = reward_sats - fee_sats
        amounts = allocate_satoshis(scores, distributable)
        now = time.time()
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute(
                "INSERT INTO blocks(hash,height,ts,reward_sats,fee_sats,distributable_sats,payout_mode,start_share_id,end_share_id) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (block_hash, height, now, reward_sats, fee_sats, distributable, mode, start_share_id, end_share_id),
            )
            for worker, amount in amounts.items():
                self.db.execute(
                    "INSERT INTO credits(block_hash,worker,score,amount_sats,status) VALUES(?,?,?,?, 'pending')",
                    (block_hash, worker, fmt_decimal(scores[worker]), amount),
                )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        if sum(amounts.values()) != distributable:
            raise AssertionError("credits do not sum to distributable block reward")
        return amounts

    def stats(self, window_seconds: int = 600) -> dict[str, Any]:
        now = time.time()
        cutoff = now - max(1, window_seconds)
        workers = self.db.execute(
            "SELECT worker, first_seen, last_seen, current_difficulty, accepted_shares, rejected_shares FROM workers ORDER BY worker"
        ).fetchall()
        output_workers = []
        for row in workers:
            shares = self.db.execute(
                "SELECT difficulty FROM shares WHERE worker=? AND ts>=?",
                (row["worker"], cutoff),
            ).fetchall()
            score = sum((as_decimal(item["difficulty"]) for item in shares), Decimal(0))
            active_start = max(float(row["first_seen"]), cutoff)
            span = max(1.0, now - active_start)
            hashrate = float(score * HASHES_PER_DIFF1 / Decimal(str(span)))
            pending_row = self.db.execute(
                "SELECT COALESCE(SUM(amount_sats),0) AS value FROM credits WHERE worker=? AND status='pending'",
                (row["worker"],),
            ).fetchone()
            output_workers.append(
                {
                    "worker": str(row["worker"]),
                    "difficulty": str(row["current_difficulty"]),
                    "accepted_shares": int(row["accepted_shares"]),
                    "rejected_shares": int(row["rejected_shares"]),
                    "window_shares": len(shares),
                    "estimated_hashrate_hs": hashrate,
                    "pending_sats": int(pending_row["value"]),
                }
            )
        block_row = self.db.execute(
            "SELECT COUNT(*) AS blocks, COALESCE(SUM(reward_sats),0) AS reward, COALESCE(SUM(fee_sats),0) AS fees, "
            "COALESCE(SUM(distributable_sats),0) AS distributable FROM blocks"
        ).fetchone()
        pending_row = self.db.execute("SELECT COALESCE(SUM(amount_sats),0) AS value FROM credits WHERE status='pending'").fetchone()
        return {
            "db": str(self.path),
            "window_seconds": window_seconds,
            "blocks": int(block_row["blocks"]),
            "reward_sats": int(block_row["reward"]),
            "pool_fee_sats": int(block_row["fees"]),
            "credited_sats": int(block_row["distributable"]),
            "pending_sats": int(pending_row["value"]),
            "workers": output_workers,
        }


@dataclass
class VardiffState:
    difficulty: Decimal
    last_share_at: float | None = None
    intervals: deque[float] = field(default_factory=lambda: deque(maxlen=8))
    last_retarget: float = field(default_factory=time.monotonic)


class AccountingPool(BASE.Pool):
    def __init__(
        self,
        *args,
        ledger: PoolLedger,
        payout_mode: str,
        pplns_shares: int,
        pool_fee_bps: int,
        vardiff_enabled: bool,
        vardiff_min: Decimal,
        vardiff_max: Decimal,
        vardiff_target_seconds: float,
        vardiff_retarget_seconds: float,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.ledger = ledger
        self.payout_mode = payout_mode
        self.pplns_shares = pplns_shares
        self.pool_fee_bps = pool_fee_bps
        self.vardiff_enabled = vardiff_enabled
        self.vardiff_min = vardiff_min
        self.vardiff_max = vardiff_max
        self.vardiff_target_seconds = vardiff_target_seconds
        self.vardiff_retarget_seconds = vardiff_retarget_seconds
        self.default_difficulty = as_decimal(self.share_difficulty)
        self._states: dict[BASE.Session, VardiffState] = {}

    def state(self, session: BASE.Session) -> VardiffState:
        state = self._states.get(session)
        if state is None:
            state = VardiffState(self.default_difficulty)
            self._states[session] = state
        return state

    async def set_difficulty(self, session: BASE.Session) -> None:
        difficulty = self.state(session).difficulty
        await self.send(
            session,
            {"id": None, "method": "mining.set_difficulty", "params": [float(difficulty)]},
        )

    async def scanner_hash_target(self, header: bytes, nonce: int, share_target: int) -> str | None:
        cmd = [
            self.scanner,
            "--header", header.hex(),
            "--target", f"{share_target:064x}",
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

    async def maybe_retarget(self, session: BASE.Session) -> None:
        state = self.state(session)
        now = time.monotonic()
        if state.last_share_at is not None:
            state.intervals.append(max(1e-6, now - state.last_share_at))
        state.last_share_at = now
        if not self.vardiff_enabled or len(state.intervals) < 4:
            return
        if now - state.last_retarget < self.vardiff_retarget_seconds:
            return
        observed = sum(state.intervals) / len(state.intervals)
        updated = next_vardiff(
            state.difficulty,
            observed,
            self.vardiff_target_seconds,
            self.vardiff_min,
            self.vardiff_max,
        )
        state.last_retarget = now
        if updated == state.difficulty:
            return
        old = state.difficulty
        state.difficulty = updated
        if session.worker:
            self.ledger.set_worker_difficulty(session.worker, updated)
        await self.set_difficulty(session)
        await self.notify(session, clean=False)
        print(
            f"crakpool vardiff worker={session.worker} old={fmt_decimal(old)} new={fmt_decimal(updated)} "
            f"observed={observed:.3f}s target={self.vardiff_target_seconds:.3f}s",
            flush=True,
        )

    def reject(self, session: BASE.Session) -> None:
        self.rejected_shares += 1
        if session.worker:
            self.ledger.record_rejected(session.worker)

    async def handle_submit(self, session: BASE.Session, request_id: Any, params: list[Any]) -> None:
        if not session.authorized:
            await self.reply(session, request_id, False, [24, "unauthorized worker", None])
            return
        if len(params) != 5:
            self.reject(session)
            await self.reply(session, request_id, False, [20, "mining.submit expects 5 params", None])
            return
        worker, job_id, extranonce2_hex, ntime_hex, nonce_hex = map(str, params)
        if worker != session.worker:
            self.reject(session)
            await self.reply(session, request_id, False, [24, "worker name does not match authorized session", None])
            return
        job = self.jobs.get(job_id)
        if job is None or self.current_job is None or job_id != self.current_job.job_id:
            self.reject(session)
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
            self.reject(session)
            await self.reply(session, request_id, False, [20, str(exc), None])
            return
        if ntime != int(job.template["curtime"]):
            self.reject(session)
            await self.reply(session, request_id, False, [20, "ntime rolling not enabled in CRAK-015", None])
            return
        share_key = (job_id, extranonce2_hex.lower(), ntime_hex.lower(), nonce_hex.lower())
        if share_key in session.seen:
            self.reject(session)
            await self.reply(session, request_id, False, [22, "duplicate share", None])
            return
        session.seen.add(share_key)

        state = self.state(session)
        share_target = BASE.difficulty_target(fmt_decimal(state.difficulty))
        full_coinbase, coinbase_txid = self.build_coinbase(job, session.extranonce1, extranonce2)
        merkle = BASE.merkle_from_coinbase(coinbase_txid, job.branch)
        header = self.build_header(job, merkle, ntime, nonce)
        block_hash = await self.scanner_hash_target(header, nonce, share_target)
        if block_hash is None:
            self.reject(session)
            await self.reply(session, request_id, False, [23, "low difficulty share", None])
            return

        is_block = int(block_hash, 16) <= job.network_target
        if is_block:
            tx_data = [bytes.fromhex(tx["data"]) for tx in job.template.get("transactions", [])]
            block = header + BASE.varint(1 + len(tx_data)) + full_coinbase + b"".join(tx_data)
            submit = await self.rpc_async("submitblock", block.hex())
            if submit not in (None, ""):
                self.reject(session)
                await self.reply(session, request_id, False, [20, f"block rejected: {submit}", None])
                return

        self.accepted_shares += 1
        share_id = self.ledger.record_share(worker, job_id, state.difficulty, block_hash, is_block)
        if is_block:
            self.blocks_found += 1
            reward_sats = int(job.template["coinbasevalue"])
            credits = self.ledger.record_block_and_allocate(
                block_hash,
                int(job.template["height"]),
                reward_sats,
                share_id,
                self.payout_mode,
                self.pplns_shares,
                self.pool_fee_bps,
            )
            print(
                f"crakpool BLOCK worker={worker} hash={block_hash} height={job.template['height']} "
                f"shares={self.accepted_shares} payout_mode={self.payout_mode} credits={sum(credits.values())}",
                flush=True,
            )
            await self.reply(session, request_id, True, None)
            await self.maybe_retarget(session)
            await self.refresh_template(force=True)
            return

        print(
            f"crakpool share worker={worker} hash={block_hash} diff={fmt_decimal(state.difficulty)} "
            f"accepted={self.accepted_shares}",
            flush=True,
        )
        await self.reply(session, request_id, True, None)
        await self.maybe_retarget(session)

    async def handle_message(self, session: BASE.Session, message: dict[str, Any]) -> None:
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
            saved = self.ledger.register_worker(worker, self.state(session).difficulty)
            saved = min(max(saved, self.vardiff_min), self.vardiff_max)
            self.state(session).difficulty = saved
            await self.reply(session, request_id, True, None)
            await self.set_difficulty(session)
            await self.notify(session, clean=True)
            return
        if method == "mining.submit":
            await self.handle_submit(session, request_id, list(params))
            return
        if method in ("mining.extranonce.subscribe", "mining.suggest_difficulty"):
            await self.reply(session, request_id, True, None)
            return
        await self.reply(session, request_id, None, [20, f"unsupported method: {method}", None])

    async def run(self) -> None:
        await self.refresh_template(force=True)
        server = await asyncio.start_server(self.handle_client, self.listen, self.port, limit=65536)
        sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
        print(
            f"crakpool ready listen={sockets} base_difficulty={self.share_difficulty} db={self.ledger.path} "
            f"payout_mode={self.payout_mode} fee_bps={self.pool_fee_bps} vardiff={str(self.vardiff_enabled).lower()}",
            flush=True,
        )
        refresher = asyncio.create_task(self.template_loop())
        try:
            async with server:
                await server.serve_forever()
        finally:
            refresher.cancel()
            await asyncio.gather(refresher, return_exceptions=True)
            self.ledger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit CRAK-015 accounting/vardiff Stratum pool")
    parser.add_argument("--network", choices=["testnet4", "regtest"], default="testnet4")
    payout = parser.add_mutually_exclusive_group(required=True)
    payout.add_argument("--wallet")
    payout.add_argument("--address")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3333)
    parser.add_argument("--share-difficulty", default="0.0001")
    parser.add_argument("--datadir", default=os.environ.get("CRAKBIT_DATADIR", str(Path.home() / ".crakbit")))
    parser.add_argument("--rpcport", type=int)
    parser.add_argument("--cli")
    parser.add_argument("--scanner")
    parser.add_argument("--db", help="SQLite ledger path; default is inside the selected datadir")
    parser.add_argument("--payout-mode", choices=["proportional", "pplns"], default="pplns")
    parser.add_argument("--pplns-shares", type=int, default=1000)
    parser.add_argument("--pool-fee-bps", type=int, default=0, help="accounting-only fee in basis points; 100 = 1%%")
    parser.add_argument("--vardiff", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--vardiff-min")
    parser.add_argument("--vardiff-max")
    parser.add_argument("--vardiff-target-seconds", type=float, default=15.0)
    parser.add_argument("--vardiff-retarget-seconds", type=float, default=90.0)
    args = parser.parse_args()

    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1..65535")
    if args.pplns_shares < 1:
        parser.error("--pplns-shares must be positive")
    if not 0 <= args.pool_fee_bps <= 10000:
        parser.error("--pool-fee-bps must be 0..10000")
    if args.vardiff_target_seconds <= 0 or args.vardiff_retarget_seconds <= 0:
        parser.error("vardiff intervals must be positive")

    base_diff = as_decimal(args.share_difficulty)
    if base_diff <= 0:
        parser.error("--share-difficulty must be positive")
    BASE.difficulty_target(fmt_decimal(base_diff))
    vardiff_min = as_decimal(args.vardiff_min) if args.vardiff_min else base_diff / Decimal(16)
    vardiff_max = as_decimal(args.vardiff_max) if args.vardiff_max else base_diff * Decimal(65536)
    if vardiff_min <= 0 or vardiff_max < vardiff_min:
        parser.error("invalid vardiff min/max")

    cli = BASE.resolve_executable(args.cli, "crakbit-cli", "crakbit-cli")
    scanner = BASE.resolve_executable(args.scanner, "crakminer-scan", "crakminer-scan")
    rpc = BASE.Rpc(cli, args.network, args.datadir, args.rpcport)
    rpc.call("getblockcount")
    address = args.address
    if args.wallet:
        address = rpc.call("getnewaddress", "", "bech32", wallet=args.wallet, parse_json=False)
    assert address
    info = rpc.call("validateaddress", address)
    if not isinstance(info, dict) or not info.get("isvalid") or not info.get("scriptPubKey"):
        raise SystemExit(f"invalid pool payout address for {args.network}: {address}")
    payout_script = bytes.fromhex(info["scriptPubKey"])

    db_path = Path(args.db) if args.db else Path(args.datadir) / f"crakpool-{args.network}.sqlite3"
    ledger = PoolLedger(db_path)
    pool = AccountingPool(
        rpc,
        scanner,
        payout_script,
        args.listen,
        args.port,
        fmt_decimal(base_diff),
        ledger=ledger,
        payout_mode=args.payout_mode,
        pplns_shares=args.pplns_shares,
        pool_fee_bps=args.pool_fee_bps,
        vardiff_enabled=args.vardiff,
        vardiff_min=vardiff_min,
        vardiff_max=vardiff_max,
        vardiff_target_seconds=args.vardiff_target_seconds,
        vardiff_retarget_seconds=args.vardiff_retarget_seconds,
    )
    print(
        f"crakpool payout={address} network={args.network} accounting_db={db_path} "
        f"payout_mode={args.payout_mode}",
        flush=True,
    )
    try:
        asyncio.run(pool.run())
    except KeyboardInterrupt:
        print("crakpool stopped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, sqlite3.Error) as exc:
        print(f"crakpool: {exc}", file=sys.stderr)
        raise SystemExit(1)
