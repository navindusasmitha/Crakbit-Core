#!/usr/bin/env python3
"""CRAK-016 Crakbit pool reconciliation and payout planning.

This tool reconciles CRAK-015 accounting records against the canonical node
chain, records worker payout addresses, and creates deterministic payout plans
from mature credits. It does not create, sign, or broadcast transactions.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

COIN = Decimal(100_000_000)


def load_base_pool():
    here = Path(__file__).resolve().parent
    for candidate in (here / "crakpool.py", here / "crakpool-base.py"):
        if not candidate.exists():
            continue
        spec = importlib.util.spec_from_file_location("crakpool_payout_base", candidate)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    raise RuntimeError("CRAK-014 base pool module not found beside crakpool-payout")


BASE = load_base_pool()


def coins_to_sats(value: Any) -> int:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid coin amount: {value}") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("coin amount must be finite and non-negative")
    sats = amount * COIN
    if sats != sats.to_integral_value():
        raise ValueError(f"coin amount has sub-satoshi precision: {value}")
    return int(sats)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


class PayoutLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise RuntimeError(f"pool ledger not found: {self.path}")
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        required = {"workers", "blocks", "credits"}
        found = {
            str(row["name"])
            for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('workers','blocks','credits')"
            ).fetchall()
        }
        if found != required:
            self.db.close()
            raise RuntimeError("not a CRAK-015 pool accounting database")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS worker_payouts (
                worker TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(worker) REFERENCES workers(worker)
            );
            CREATE TABLE IF NOT EXISTS block_reconciliation (
                block_hash TEXT PRIMARY KEY,
                canonical INTEGER NOT NULL,
                confirmations INTEGER NOT NULL,
                tip_height INTEGER NOT NULL,
                tip_hash TEXT NOT NULL,
                checked_at REAL NOT NULL,
                FOREIGN KEY(block_hash) REFERENCES blocks(hash)
            );
            CREATE INDEX IF NOT EXISTS block_reconciliation_canonical
                ON block_reconciliation(canonical, confirmations);
            CREATE TABLE IF NOT EXISTS payout_batches (
                id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                state TEXT NOT NULL,
                network TEXT NOT NULL,
                tip_height INTEGER NOT NULL,
                tip_hash TEXT NOT NULL,
                maturity INTEGER NOT NULL,
                minimum_sats INTEGER NOT NULL,
                total_sats INTEGER NOT NULL,
                output_count INTEGER NOT NULL,
                funding_checked INTEGER NOT NULL DEFAULT 0,
                wallet_trusted_sats INTEGER
            );
            CREATE TABLE IF NOT EXISTS payout_items (
                batch_id TEXT NOT NULL,
                worker TEXT NOT NULL,
                address TEXT NOT NULL,
                amount_sats INTEGER NOT NULL,
                PRIMARY KEY(batch_id, worker),
                FOREIGN KEY(batch_id) REFERENCES payout_batches(id),
                FOREIGN KEY(worker) REFERENCES workers(worker)
            );
            CREATE TABLE IF NOT EXISTS payout_credit_links (
                batch_id TEXT NOT NULL,
                block_hash TEXT NOT NULL,
                worker TEXT NOT NULL,
                amount_sats INTEGER NOT NULL,
                PRIMARY KEY(batch_id, block_hash, worker),
                FOREIGN KEY(batch_id) REFERENCES payout_batches(id),
                FOREIGN KEY(block_hash, worker) REFERENCES credits(block_hash, worker)
            );
            CREATE INDEX IF NOT EXISTS payout_batches_state ON payout_batches(state);
            CREATE INDEX IF NOT EXISTS payout_credit_links_credit
                ON payout_credit_links(block_hash, worker);
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def register_address(self, worker: str, address: str) -> None:
        worker_row = self.db.execute("SELECT worker FROM workers WHERE worker=?", (worker,)).fetchone()
        if worker_row is None:
            raise RuntimeError(f"unknown worker: {worker}")
        self.db.execute(
            """
            INSERT INTO worker_payouts(worker,address,updated_at) VALUES(?,?,?)
            ON CONFLICT(worker) DO UPDATE SET address=excluded.address, updated_at=excluded.updated_at
            """,
            (worker, address, time.time()),
        )
        self.db.commit()

    def _invalidate_batches_for_orphans(self) -> list[str]:
        rows = self.db.execute(
            """
            SELECT DISTINCT pcl.batch_id
            FROM payout_credit_links AS pcl
            JOIN block_reconciliation AS br ON br.block_hash=pcl.block_hash
            JOIN payout_batches AS pb ON pb.id=pcl.batch_id
            WHERE pb.state='planned' AND br.canonical=0
            ORDER BY pcl.batch_id
            """
        ).fetchall()
        invalidated = [str(row["batch_id"]) for row in rows]
        for batch_id in invalidated:
            self.db.execute("UPDATE payout_batches SET state='invalidated' WHERE id=?", (batch_id,))
            linked = self.db.execute(
                "SELECT block_hash, worker FROM payout_credit_links WHERE batch_id=? ORDER BY block_hash,worker",
                (batch_id,),
            ).fetchall()
            for item in linked:
                rec = self.db.execute(
                    "SELECT canonical FROM block_reconciliation WHERE block_hash=?",
                    (item["block_hash"],),
                ).fetchone()
                status = "pending" if rec is not None and int(rec["canonical"]) == 1 else "orphaned"
                self.db.execute(
                    "UPDATE credits SET status=? WHERE block_hash=? AND worker=? AND status='planned'",
                    (status, item["block_hash"], item["worker"]),
                )
        return invalidated

    def reconcile_snapshot(
        self,
        tip_height: int,
        tip_hash: str,
        canonical_hashes: dict[int, str | None],
    ) -> dict[str, Any]:
        if tip_height < 0 or len(tip_hash) != 64:
            raise ValueError("invalid chain tip snapshot")
        blocks = self.db.execute("SELECT hash,height FROM blocks ORDER BY height,hash").fetchall()
        now = time.time()
        active = 0
        orphaned = 0
        with self.db:
            for block in blocks:
                block_hash = str(block["hash"]).lower()
                height = int(block["height"])
                expected = canonical_hashes.get(height)
                canonical = expected is not None and expected.lower() == block_hash
                confirmations = tip_height - height + 1 if canonical and tip_height >= height else 0
                self.db.execute(
                    """
                    INSERT INTO block_reconciliation(
                        block_hash,canonical,confirmations,tip_height,tip_hash,checked_at
                    ) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(block_hash) DO UPDATE SET
                        canonical=excluded.canonical,
                        confirmations=excluded.confirmations,
                        tip_height=excluded.tip_height,
                        tip_hash=excluded.tip_hash,
                        checked_at=excluded.checked_at
                    """,
                    (block_hash, 1 if canonical else 0, confirmations, tip_height, tip_hash.lower(), now),
                )
                if canonical:
                    active += 1
                else:
                    orphaned += 1

            self.db.execute(
                """
                UPDATE credits SET status='pending'
                WHERE status='orphaned'
                  AND EXISTS (
                    SELECT 1 FROM block_reconciliation br
                    WHERE br.block_hash=credits.block_hash AND br.canonical=1
                  )
                """
            )
            invalidated = self._invalidate_batches_for_orphans()
            self.db.execute(
                """
                UPDATE credits SET status='orphaned'
                WHERE status IN ('pending','planned')
                  AND EXISTS (
                    SELECT 1 FROM block_reconciliation br
                    WHERE br.block_hash=credits.block_hash AND br.canonical=0
                  )
                """
            )

        return {
            "tip_height": tip_height,
            "tip_hash": tip_hash.lower(),
            "blocks": len(blocks),
            "canonical_blocks": active,
            "orphaned_blocks": orphaned,
            "invalidated_batches": invalidated,
        }

    def _snapshot_is_current(self, tip_height: int, tip_hash: str) -> bool:
        blocks = int(self.db.execute("SELECT COUNT(*) AS n FROM blocks").fetchone()["n"])
        if blocks == 0:
            return True
        row = self.db.execute(
            "SELECT COUNT(*) AS n FROM block_reconciliation WHERE tip_height=? AND tip_hash=?",
            (tip_height, tip_hash.lower()),
        ).fetchone()
        return int(row["n"]) == blocks

    def create_plan(
        self,
        *,
        network: str,
        tip_height: int,
        tip_hash: str,
        maturity: int,
        minimum_sats: int,
        max_outputs: int,
        funding_checked: bool = False,
        wallet_trusted_sats: int | None = None,
        fee_reserve_sats: int = 0,
    ) -> dict[str, Any] | None:
        if maturity < 1:
            raise ValueError("maturity must be positive")
        if minimum_sats < 1:
            raise ValueError("minimum payout must be positive")
        if max_outputs < 1:
            raise ValueError("max outputs must be positive")
        if fee_reserve_sats < 0:
            raise ValueError("fee reserve cannot be negative")
        if not self._snapshot_is_current(tip_height, tip_hash):
            raise RuntimeError("ledger reconciliation snapshot is stale or incomplete")

        rows = self.db.execute(
            """
            SELECT c.block_hash, c.worker, c.amount_sats, b.height, wp.address
            FROM credits AS c
            JOIN blocks AS b ON b.hash=c.block_hash
            JOIN block_reconciliation AS br ON br.block_hash=c.block_hash
            JOIN worker_payouts AS wp ON wp.worker=c.worker
            WHERE c.status='pending' AND br.canonical=1 AND br.confirmations>=?
            ORDER BY c.worker, b.height, c.block_hash
            """,
            (maturity,),
        ).fetchall()

        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            worker = str(row["worker"])
            entry = grouped.setdefault(
                worker,
                {"worker": worker, "address": str(row["address"]), "amount_sats": 0, "credits": []},
            )
            entry["amount_sats"] += int(row["amount_sats"])
            entry["credits"].append(
                {"block_hash": str(row["block_hash"]), "amount_sats": int(row["amount_sats"])}
            )

        selected = [
            grouped[worker]
            for worker in sorted(grouped)
            if int(grouped[worker]["amount_sats"]) >= minimum_sats
        ][:max_outputs]
        if not selected:
            return None

        total_sats = sum(int(item["amount_sats"]) for item in selected)
        required = total_sats + fee_reserve_sats
        if funding_checked:
            if wallet_trusted_sats is None:
                raise RuntimeError("funding check requested without wallet balance")
            if wallet_trusted_sats < required:
                raise RuntimeError(
                    f"wallet trusted balance {wallet_trusted_sats} sats is below planned "
                    f"{total_sats} + fee reserve {fee_reserve_sats}"
                )

        plan_payload = {
            "network": network,
            "tip_height": tip_height,
            "tip_hash": tip_hash.lower(),
            "maturity": maturity,
            "minimum_sats": minimum_sats,
            "outputs": [
                {
                    "worker": item["worker"],
                    "address": item["address"],
                    "amount_sats": int(item["amount_sats"]),
                    "credits": item["credits"],
                }
                for item in selected
            ],
        }
        batch_id = hashlib.sha256(canonical_json(plan_payload)).hexdigest()[:32]

        with self.db:
            existing = self.db.execute("SELECT id FROM payout_batches WHERE id=?", (batch_id,)).fetchone()
            if existing is not None:
                return self.get_batch(batch_id)
            self.db.execute(
                """
                INSERT INTO payout_batches(
                    id,created_at,state,network,tip_height,tip_hash,maturity,
                    minimum_sats,total_sats,output_count,funding_checked,wallet_trusted_sats
                ) VALUES(?,?,'planned',?,?,?,?,?,?,?,?,?)
                """,
                (
                    batch_id,
                    time.time(),
                    network,
                    tip_height,
                    tip_hash.lower(),
                    maturity,
                    minimum_sats,
                    total_sats,
                    len(selected),
                    1 if funding_checked else 0,
                    wallet_trusted_sats,
                ),
            )
            for item in selected:
                self.db.execute(
                    "INSERT INTO payout_items(batch_id,worker,address,amount_sats) VALUES(?,?,?,?)",
                    (batch_id, item["worker"], item["address"], int(item["amount_sats"])),
                )
                for credit in item["credits"]:
                    updated = self.db.execute(
                        "UPDATE credits SET status='planned' WHERE block_hash=? AND worker=? AND status='pending'",
                        (credit["block_hash"], item["worker"]),
                    )
                    if updated.rowcount != 1:
                        raise RuntimeError("credit state changed while building payout plan")
                    self.db.execute(
                        """
                        INSERT INTO payout_credit_links(batch_id,block_hash,worker,amount_sats)
                        VALUES(?,?,?,?)
                        """,
                        (batch_id, credit["block_hash"], item["worker"], credit["amount_sats"]),
                    )

        return self.get_batch(batch_id)

    def cancel_batch(self, batch_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT state FROM payout_batches WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"unknown payout batch: {batch_id}")
        if str(row["state"]) != "planned":
            raise RuntimeError(f"batch {batch_id} is not cancellable from state {row['state']}")
        with self.db:
            links = self.db.execute(
                "SELECT block_hash,worker FROM payout_credit_links WHERE batch_id=?",
                (batch_id,),
            ).fetchall()
            for link in links:
                rec = self.db.execute(
                    "SELECT canonical FROM block_reconciliation WHERE block_hash=?",
                    (link["block_hash"],),
                ).fetchone()
                status = "pending" if rec is not None and int(rec["canonical"]) == 1 else "orphaned"
                self.db.execute(
                    "UPDATE credits SET status=? WHERE block_hash=? AND worker=? AND status='planned'",
                    (status, link["block_hash"], link["worker"]),
                )
            self.db.execute("UPDATE payout_batches SET state='cancelled' WHERE id=?", (batch_id,))
        return self.get_batch(batch_id)

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        batch = self.db.execute("SELECT * FROM payout_batches WHERE id=?", (batch_id,)).fetchone()
        if batch is None:
            raise RuntimeError(f"unknown payout batch: {batch_id}")
        items = self.db.execute(
            "SELECT worker,address,amount_sats FROM payout_items WHERE batch_id=? ORDER BY worker",
            (batch_id,),
        ).fetchall()
        return {
            "id": str(batch["id"]),
            "state": str(batch["state"]),
            "network": str(batch["network"]),
            "tip_height": int(batch["tip_height"]),
            "tip_hash": str(batch["tip_hash"]),
            "maturity": int(batch["maturity"]),
            "minimum_sats": int(batch["minimum_sats"]),
            "total_sats": int(batch["total_sats"]),
            "output_count": int(batch["output_count"]),
            "funding_checked": bool(batch["funding_checked"]),
            "wallet_trusted_sats": (
                int(batch["wallet_trusted_sats"]) if batch["wallet_trusted_sats"] is not None else None
            ),
            "outputs": [
                {
                    "worker": str(item["worker"]),
                    "address": str(item["address"]),
                    "amount_sats": int(item["amount_sats"]),
                }
                for item in items
            ],
        }

    def status(self) -> dict[str, Any]:
        credit_rows = self.db.execute(
            "SELECT status,COUNT(*) AS n,COALESCE(SUM(amount_sats),0) AS sats FROM credits GROUP BY status ORDER BY status"
        ).fetchall()
        block_rows = self.db.execute(
            "SELECT canonical,COUNT(*) AS n FROM block_reconciliation GROUP BY canonical ORDER BY canonical"
        ).fetchall()
        batch_rows = self.db.execute(
            "SELECT state,COUNT(*) AS n FROM payout_batches GROUP BY state ORDER BY state"
        ).fetchall()
        return {
            "db": str(self.path),
            "credits": {
                str(row["status"]): {"count": int(row["n"]), "sats": int(row["sats"])}
                for row in credit_rows
            },
            "reconciled_blocks": {
                ("canonical" if int(row["canonical"]) else "orphaned"): int(row["n"])
                for row in block_rows
            },
            "batches": {str(row["state"]): int(row["n"]) for row in batch_rows},
            "registered_workers": int(
                self.db.execute("SELECT COUNT(*) AS n FROM worker_payouts").fetchone()["n"]
            ),
        }


def chain_snapshot(rpc: Any, ledger: PayoutLedger) -> tuple[int, str, dict[int, str | None]]:
    tip_height = int(rpc.call("getblockcount"))
    tip_hash = str(rpc.call("getblockhash", str(tip_height), parse_json=False)).strip().lower()
    if len(tip_hash) != 64:
        raise RuntimeError(f"invalid tip hash from node: {tip_hash}")
    heights = [
        int(row["height"])
        for row in ledger.db.execute("SELECT DISTINCT height FROM blocks ORDER BY height").fetchall()
    ]
    hashes: dict[int, str | None] = {}
    for height in heights:
        if height > tip_height:
            hashes[height] = None
            continue
        block_hash = str(rpc.call("getblockhash", str(height), parse_json=False)).strip().lower()
        if len(block_hash) != 64:
            raise RuntimeError(f"invalid block hash at height {height}: {block_hash}")
        hashes[height] = block_hash
    return tip_height, tip_hash, hashes


def wallet_trusted_balance_sats(rpc: Any, wallet: str) -> int:
    balances = rpc.call("getbalances", wallet=wallet)
    if not isinstance(balances, dict):
        raise RuntimeError("unexpected getbalances response")
    mine = balances.get("mine")
    if not isinstance(mine, dict) or "trusted" not in mine:
        raise RuntimeError("wallet getbalances response has no mine.trusted")
    return coins_to_sats(mine["trusted"])


def add_rpc_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--network", choices=["testnet4", "regtest"], default="testnet4")
    parser.add_argument("--datadir", default=os.environ.get("CRAKBIT_DATADIR", str(Path.home() / ".crakbit")))
    parser.add_argument("--rpcport", type=int)
    parser.add_argument("--cli")


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit CRAK-016 payout reconciliation/planner")
    parser.add_argument("--db", required=True, help="CRAK-015 SQLite accounting database")
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register", help="register or replace a worker payout address")
    add_rpc_args(register)
    register.add_argument("--worker", required=True)
    register.add_argument("--address", required=True)

    reconcile = sub.add_parser("reconcile", help="reconcile pool blocks against the canonical chain")
    add_rpc_args(reconcile)

    plan = sub.add_parser("plan", help="reconcile and create a mature-credit payout batch")
    add_rpc_args(plan)
    plan.add_argument("--maturity", type=int, default=100)
    plan.add_argument("--minimum-sats", type=int, default=100_000)
    plan.add_argument("--max-outputs", type=int, default=100)
    plan.add_argument("--wallet", help="optional local pool wallet used only for trusted-balance verification")
    plan.add_argument("--fee-reserve-sats", type=int, default=10_000)

    show = sub.add_parser("show", help="show a payout batch")
    show.add_argument("--batch", required=True)
    cancel = sub.add_parser("cancel", help="cancel an unbroadcast planned batch")
    cancel.add_argument("--batch", required=True)
    sub.add_parser("status", help="show reconciliation and payout ledger status")
    args = parser.parse_args()

    ledger = PayoutLedger(args.db)
    try:
        if args.command == "status":
            print(json.dumps(ledger.status(), sort_keys=True, indent=2))
            return 0
        if args.command == "show":
            print(json.dumps(ledger.get_batch(args.batch), sort_keys=True, indent=2))
            return 0
        if args.command == "cancel":
            print(json.dumps(ledger.cancel_batch(args.batch), sort_keys=True, indent=2))
            return 0

        cli = BASE.resolve_executable(args.cli, "crakbit-cli", "crakbit-cli")
        rpc = BASE.Rpc(cli, args.network, args.datadir, args.rpcport)
        rpc.call("getblockcount")

        if args.command == "register":
            info = rpc.call("validateaddress", args.address)
            if not isinstance(info, dict) or not info.get("isvalid"):
                raise RuntimeError(f"invalid payout address for {args.network}: {args.address}")
            ledger.register_address(args.worker, args.address)
            print(json.dumps({"worker": args.worker, "address": args.address, "registered": True}, sort_keys=True))
            return 0

        tip_height, tip_hash, hashes = chain_snapshot(rpc, ledger)
        reconciled = ledger.reconcile_snapshot(tip_height, tip_hash, hashes)
        if args.command == "reconcile":
            print(json.dumps(reconciled, sort_keys=True, indent=2))
            return 0

        if args.maturity < 1:
            parser.error("--maturity must be positive")
        if args.minimum_sats < 1:
            parser.error("--minimum-sats must be positive")
        if args.max_outputs < 1:
            parser.error("--max-outputs must be positive")
        if args.fee_reserve_sats < 0:
            parser.error("--fee-reserve-sats cannot be negative")

        funding_checked = bool(args.wallet)
        trusted = wallet_trusted_balance_sats(rpc, args.wallet) if args.wallet else None
        batch = ledger.create_plan(
            network=args.network,
            tip_height=tip_height,
            tip_hash=tip_hash,
            maturity=args.maturity,
            minimum_sats=args.minimum_sats,
            max_outputs=args.max_outputs,
            funding_checked=funding_checked,
            wallet_trusted_sats=trusted,
            fee_reserve_sats=args.fee_reserve_sats,
        )
        print(json.dumps({"reconciliation": reconciled, "batch": batch, "broadcast_enabled": False}, sort_keys=True, indent=2))
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, sqlite3.Error) as exc:
        print(f"crakpool-payout: {exc}", file=sys.stderr)
        raise SystemExit(1)
