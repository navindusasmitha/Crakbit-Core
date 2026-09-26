#!/usr/bin/env python3
"""Read CRAK-015 pool accounting state without touching the node or pool process."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

HASHES_PER_DIFF1 = Decimal(2**32)


def dec(value: str) -> Decimal:
    try:
        out = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid stored difficulty: {value}") from exc
    return out


def read_stats(path: Path, window_seconds: int) -> dict:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    now = time.time()
    cutoff = now - window_seconds
    workers = []
    for row in db.execute(
        "SELECT worker, first_seen, last_seen, current_difficulty, accepted_shares, rejected_shares FROM workers ORDER BY worker"
    ):
        share_rows = db.execute(
            "SELECT difficulty FROM shares WHERE worker=? AND ts>=?",
            (row["worker"], cutoff),
        ).fetchall()
        score = sum((dec(item["difficulty"]) for item in share_rows), Decimal(0))
        active_start = max(float(row["first_seen"]), cutoff)
        span = max(1.0, now - active_start)
        hashrate = float(score * HASHES_PER_DIFF1 / Decimal(str(span)))
        pending = db.execute(
            "SELECT COALESCE(SUM(amount_sats),0) AS value FROM credits WHERE worker=? AND status='pending'",
            (row["worker"],),
        ).fetchone()
        workers.append(
            {
                "worker": str(row["worker"]),
                "difficulty": str(row["current_difficulty"]),
                "accepted_shares": int(row["accepted_shares"]),
                "rejected_shares": int(row["rejected_shares"]),
                "window_shares": len(share_rows),
                "estimated_hashrate_hs": hashrate,
                "pending_sats": int(pending["value"]),
            }
        )
    blocks = db.execute(
        "SELECT COUNT(*) AS count, COALESCE(SUM(reward_sats),0) AS reward, COALESCE(SUM(fee_sats),0) AS fees, "
        "COALESCE(SUM(distributable_sats),0) AS credited FROM blocks"
    ).fetchone()
    pending = db.execute("SELECT COALESCE(SUM(amount_sats),0) AS value FROM credits WHERE status='pending'").fetchone()
    result = {
        "db": str(path),
        "window_seconds": window_seconds,
        "blocks": int(blocks["count"]),
        "reward_sats": int(blocks["reward"]),
        "pool_fee_sats": int(blocks["fees"]),
        "credited_sats": int(blocks["credited"]),
        "pending_sats": int(pending["value"]),
        "workers": workers,
    }
    db.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit CRAK-015 pool ledger statistics")
    parser.add_argument("--db", required=True)
    parser.add_argument("--window", type=int, default=600, help="hashrate window in seconds")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.window < 1:
        parser.error("--window must be positive")
    path = Path(args.db)
    if not path.exists():
        parser.error(f"database does not exist: {path}")
    stats = read_stats(path, args.window)
    if args.json:
        print(json.dumps(stats, indent=2, sort_keys=True))
        return 0
    print(
        f"blocks={stats['blocks']} reward_sats={stats['reward_sats']} fee_sats={stats['pool_fee_sats']} "
        f"pending_sats={stats['pending_sats']} window={stats['window_seconds']}s"
    )
    for worker in stats["workers"]:
        print(
            f"worker={worker['worker']} diff={worker['difficulty']} accepted={worker['accepted_shares']} "
            f"rejected={worker['rejected_shares']} hashrate={worker['estimated_hashrate_hs']:.2f}H/s "
            f"pending_sats={worker['pending_sats']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
