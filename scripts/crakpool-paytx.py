#!/usr/bin/env python3
"""CRAK-017 operator-controlled payout transaction lifecycle.

Builds and persists an unsigned/fundable PSBT for a CRAK-016 planned batch,
allows an operator to attach the txid after external signing/broadcast, tracks
confirmations, and settles linked credits only after the confirmation gate.
This tool never signs or broadcasts funds.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

COIN = Decimal(100_000_000)


def load_payout():
    path = Path(__file__).resolve().parent / "crakpool-payout.py"
    spec = importlib.util.spec_from_file_location("crakpool_paytx_payout", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CRAK-016 crakpool-payout.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


PAYOUT = load_payout()
BASE = PAYOUT.BASE


def sats_to_coins(sats: int) -> str:
    if sats < 0:
        raise ValueError("negative amount")
    return format(Decimal(sats) / COIN, ".8f")


class PaymentLedger(PAYOUT.PayoutLedger):
    def __init__(self, path: str | Path):
        super().__init__(path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS payout_transactions (
                batch_id TEXT PRIMARY KEY,
                psbt TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                txid TEXT UNIQUE,
                attached_at REAL,
                confirmations INTEGER NOT NULL DEFAULT 0,
                confirmed_height INTEGER,
                last_checked_at REAL,
                last_error TEXT,
                estimated_fee_sats INTEGER,
                FOREIGN KEY(batch_id) REFERENCES payout_batches(id)
            );
            CREATE INDEX IF NOT EXISTS payout_transactions_state
                ON payout_transactions(state);
            """
        )
        self.db.commit()

    def get_payment(self, batch_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM payout_transactions WHERE batch_id=?", (batch_id,)).fetchone()
        if row is None:
            return None
        return {
            "batch_id": str(row["batch_id"]),
            "psbt": str(row["psbt"]),
            "state": str(row["state"]),
            "created_at": float(row["created_at"]),
            "txid": str(row["txid"]) if row["txid"] is not None else None,
            "attached_at": float(row["attached_at"]) if row["attached_at"] is not None else None,
            "confirmations": int(row["confirmations"]),
            "confirmed_height": int(row["confirmed_height"]) if row["confirmed_height"] is not None else None,
            "last_checked_at": float(row["last_checked_at"]) if row["last_checked_at"] is not None else None,
            "last_error": row["last_error"],
            "estimated_fee_sats": int(row["estimated_fee_sats"]) if row["estimated_fee_sats"] is not None else None,
        }

    def persist_psbt(self, batch_id: str, psbt: str, fee_sats: int | None) -> dict[str, Any]:
        batch = self.db.execute("SELECT state FROM payout_batches WHERE id=?", (batch_id,)).fetchone()
        if batch is None:
            raise RuntimeError(f"unknown payout batch: {batch_id}")
        if str(batch["state"]) != "planned":
            existing = self.get_payment(batch_id)
            if existing is not None:
                return existing
            raise RuntimeError(f"batch {batch_id} is not planned")
        now = time.time()
        with self.db:
            self.db.execute(
                "INSERT INTO payout_transactions(batch_id,psbt,state,created_at,estimated_fee_sats) VALUES(?,?, 'psbt_ready',?,?)",
                (batch_id, psbt, now, fee_sats),
            )
            self.db.execute("UPDATE payout_batches SET state='psbt_ready' WHERE id=? AND state='planned'", (batch_id,))
        return self.get_payment(batch_id)  # type: ignore[return-value]

    def attach_txid(self, batch_id: str, txid: str) -> dict[str, Any]:
        if len(txid) != 64 or any(c not in "0123456789abcdefABCDEF" for c in txid):
            raise ValueError("txid must be 64 hex characters")
        row = self.get_payment(batch_id)
        if row is None:
            raise RuntimeError("build the batch PSBT first")
        if row["state"] not in {"psbt_ready", "broadcast", "confirmed", "paid"}:
            raise RuntimeError(f"cannot attach txid in state {row['state']}")
        if row["txid"] is not None and row["txid"] != txid.lower():
            raise RuntimeError("different txid already attached")
        with self.db:
            self.db.execute(
                "UPDATE payout_transactions SET txid=?,state='broadcast',attached_at=COALESCE(attached_at,?),last_error=NULL WHERE batch_id=? AND state='psbt_ready'",
                (txid.lower(), time.time(), batch_id),
            )
            self.db.execute("UPDATE payout_batches SET state='broadcast' WHERE id=? AND state='psbt_ready'", (batch_id,))
        return self.get_payment(batch_id)  # type: ignore[return-value]

    def record_check(self, batch_id: str, confirmations: int, height: int | None, error: str | None = None) -> dict[str, Any]:
        row = self.get_payment(batch_id)
        if row is None or row["txid"] is None:
            raise RuntimeError("no broadcast txid attached")
        confirmations = max(0, int(confirmations))
        state = "confirmed" if confirmations > 0 else "broadcast"
        if row["state"] == "paid":
            state = "paid"
        with self.db:
            self.db.execute(
                "UPDATE payout_transactions SET state=?,confirmations=?,confirmed_height=?,last_checked_at=?,last_error=? WHERE batch_id=?",
                (state, confirmations, height, time.time(), error, batch_id),
            )
            if state == "confirmed":
                self.db.execute("UPDATE payout_batches SET state='confirmed' WHERE id=? AND state='broadcast'", (batch_id,))
            elif state == "broadcast":
                self.db.execute("UPDATE payout_batches SET state='broadcast' WHERE id=? AND state='confirmed'", (batch_id,))
        return self.get_payment(batch_id)  # type: ignore[return-value]

    def settle(self, batch_id: str, required_confirmations: int) -> dict[str, Any]:
        row = self.get_payment(batch_id)
        if row is None:
            raise RuntimeError("unknown payment")
        if required_confirmations < 1:
            raise ValueError("required confirmations must be positive")
        if row["state"] != "confirmed" or int(row["confirmations"]) < required_confirmations:
            raise RuntimeError(f"payment has {row['confirmations']} confirmations; need {required_confirmations}")
        with self.db:
            links = self.db.execute(
                "SELECT block_hash,worker FROM payout_credit_links WHERE batch_id=? ORDER BY block_hash,worker",
                (batch_id,),
            ).fetchall()
            for link in links:
                cur = self.db.execute(
                    "UPDATE credits SET status='paid' WHERE block_hash=? AND worker=? AND status='planned'",
                    (link["block_hash"], link["worker"]),
                )
                if cur.rowcount != 1:
                    status = self.db.execute(
                        "SELECT status FROM credits WHERE block_hash=? AND worker=?",
                        (link["block_hash"], link["worker"]),
                    ).fetchone()
                    if status is None or str(status["status"]) != "paid":
                        raise RuntimeError("credit state changed before settlement")
            self.db.execute("UPDATE payout_transactions SET state='paid' WHERE batch_id=?", (batch_id,))
            self.db.execute("UPDATE payout_batches SET state='paid' WHERE id=?", (batch_id,))
        return self.get_payment(batch_id)  # type: ignore[return-value]


def rpc_call(rpc: Any, method: str, *params: Any, wallet: str | None = None, parse_json: bool = True):
    encoded: list[str] = []
    for p in params:
        if isinstance(p, (dict, list, bool, int, float)) or p is None:
            encoded.append(json.dumps(p, separators=(",", ":"), sort_keys=True))
        else:
            encoded.append(str(p))
    return rpc.call(method, *encoded, wallet=wallet, parse_json=parse_json)


def batch_outputs(batch: dict[str, Any]) -> list[dict[str, str]]:
    return [{str(item["address"]): sats_to_coins(int(item["amount_sats"]))} for item in batch["outputs"]]


def build_psbt(ledger: PaymentLedger, rpc: Any, batch_id: str, wallet: str, fee_rate: Decimal) -> dict[str, Any]:
    if fee_rate <= 0:
        raise ValueError("fee rate must be positive")
    tip_height, tip_hash, hashes = PAYOUT.chain_snapshot(rpc, ledger)
    ledger.reconcile_snapshot(tip_height, tip_hash, hashes)
    batch = ledger.get_batch(batch_id)
    if batch["state"] != "planned":
        existing = ledger.get_payment(batch_id)
        if existing is not None:
            return existing
        raise RuntimeError(f"batch {batch_id} is {batch['state']}; refusing PSBT creation")
    options = {
        "add_inputs": True,
        "include_unsafe": False,
        "lock_unspents": True,
        "replaceable": True,
        "fee_rate": float(fee_rate),
    }
    result = rpc_call(rpc, "walletcreatefundedpsbt", [], batch_outputs(batch), 0, options, True, wallet=wallet)
    if not isinstance(result, dict) or not result.get("psbt"):
        raise RuntimeError("walletcreatefundedpsbt returned no PSBT")
    fee_sats = PAYOUT.coins_to_sats(result.get("fee", 0)) if "fee" in result else None
    return ledger.persist_psbt(batch_id, str(result["psbt"]), fee_sats)


def check_payment(ledger: PaymentLedger, rpc: Any, batch_id: str, wallet: str) -> dict[str, Any]:
    row = ledger.get_payment(batch_id)
    if row is None or row["txid"] is None:
        raise RuntimeError("no broadcast txid attached")
    try:
        info = rpc_call(rpc, "gettransaction", row["txid"], True, True, wallet=wallet)
    except RuntimeError as exc:
        with ledger.db:
            ledger.db.execute(
                "UPDATE payout_transactions SET last_checked_at=?,last_error=? WHERE batch_id=?",
                (time.time(), str(exc), batch_id),
            )
        return ledger.get_payment(batch_id)  # type: ignore[return-value]
    if not isinstance(info, dict):
        raise RuntimeError("unexpected gettransaction response")
    confirmations = max(0, int(info.get("confirmations", 0)))
    height = None
    blockhash = info.get("blockhash")
    if confirmations > 0 and blockhash:
        header = rpc_call(rpc, "getblockheader", str(blockhash))
        if isinstance(header, dict) and "height" in header:
            height = int(header["height"])
    return ledger.record_check(batch_id, confirmations, height)


def add_rpc_args(parser: argparse.ArgumentParser, wallet: bool = True) -> None:
    PAYOUT.add_rpc_args(parser)
    if wallet:
        parser.add_argument("--wallet", required=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit CRAK-017 operator-controlled payout lifecycle")
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-psbt", help="create and persist a funded unsigned PSBT; never signs or broadcasts")
    add_rpc_args(build)
    build.add_argument("--batch", required=True)
    build.add_argument("--fee-rate", type=Decimal, default=Decimal("1.0"), help="sat/vB")

    attach = sub.add_parser("attach-txid", help="record txid after operator signs and broadcasts externally")
    attach.add_argument("--batch", required=True)
    attach.add_argument("--txid", required=True)

    check = sub.add_parser("check", help="refresh confirmations for an attached txid")
    add_rpc_args(check)
    check.add_argument("--batch", required=True)

    settle = sub.add_parser("settle", help="mark linked credits paid after confirmation gate")
    add_rpc_args(settle)
    settle.add_argument("--batch", required=True)
    settle.add_argument("--confirmations", type=int, default=6)

    show = sub.add_parser("show")
    show.add_argument("--batch", required=True)
    args = parser.parse_args()

    ledger = PaymentLedger(args.db)
    try:
        if args.command == "show":
            row = ledger.get_payment(args.batch)
            if row is None:
                raise RuntimeError("batch has no CRAK-017 payment record")
            print(json.dumps(row, sort_keys=True, indent=2))
            return 0
        if args.command == "attach-txid":
            print(json.dumps(ledger.attach_txid(args.batch, args.txid), sort_keys=True, indent=2))
            return 0
        cli = BASE.resolve_executable(args.cli, "crakbit-cli", "crakbit-cli")
        rpc = BASE.Rpc(cli, args.network, args.datadir, args.rpcport)
        rpc.call("getblockcount")
        if args.command == "build-psbt":
            result = build_psbt(ledger, rpc, args.batch, args.wallet, args.fee_rate)
        elif args.command == "check":
            result = check_payment(ledger, rpc, args.batch, args.wallet)
        elif args.command == "settle":
            result = check_payment(ledger, rpc, args.batch, args.wallet)
            if result["state"] != "paid":
                result = ledger.settle(args.batch, args.confirmations)
        else:
            raise RuntimeError("unknown command")
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, sqlite3.Error) as exc:
        print(f"crakpool-paytx: {exc}", file=sys.stderr)
        raise SystemExit(1)
