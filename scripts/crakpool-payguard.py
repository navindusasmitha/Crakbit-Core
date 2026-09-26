#!/usr/bin/env python3
"""CRAK-018 payout preflight, guarded attach, and cancellation recovery.

This command is an operator safety layer on top of CRAK-017. It never signs a
PSBT and never broadcasts a transaction. It re-checks payout source blocks and
PSBT recipients immediately before external signing/broadcast, records an audit
preflight, can require a fresh successful preflight before txid attachment, and
can safely unlock/cancel an unbroadcast PSBT only after explicit operator
attestation.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any


def load_paytx():
    path = Path(__file__).resolve().parent / "crakpool-paytx.py"
    spec = importlib.util.spec_from_file_location("crakpool_payguard_paytx", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CRAK-017 crakpool-paytx.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


PAYTX = load_paytx()
PAYOUT = PAYTX.PAYOUT
BASE = PAYTX.BASE


class GuardLedger(PAYTX.PaymentLedger):
    def __init__(self, path: str | Path):
        super().__init__(path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS payout_preflights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                checked_at REAL NOT NULL,
                tip_height INTEGER NOT NULL,
                tip_hash TEXT NOT NULL,
                valid INTEGER NOT NULL,
                error TEXT,
                input_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(batch_id) REFERENCES payout_batches(id)
            );
            CREATE INDEX IF NOT EXISTS payout_preflights_batch_time
                ON payout_preflights(batch_id, checked_at DESC);
            """
        )
        self.db.commit()

    def record_preflight(
        self,
        batch_id: str,
        tip_height: int,
        tip_hash: str,
        valid: bool,
        *,
        error: str | None = None,
        input_count: int = 0,
    ) -> dict[str, Any]:
        checked_at = time.time()
        with self.db:
            self.db.execute(
                """
                INSERT INTO payout_preflights(
                    batch_id,checked_at,tip_height,tip_hash,valid,error,input_count
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    batch_id,
                    checked_at,
                    int(tip_height),
                    str(tip_hash).lower(),
                    1 if valid else 0,
                    error,
                    int(input_count),
                ),
            )
        row = self.latest_preflight(batch_id)
        assert row is not None
        return row

    def latest_preflight(self, batch_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            """
            SELECT id,batch_id,checked_at,tip_height,tip_hash,valid,error,input_count
            FROM payout_preflights
            WHERE batch_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (batch_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "batch_id": str(row["batch_id"]),
            "checked_at": float(row["checked_at"]),
            "tip_height": int(row["tip_height"]),
            "tip_hash": str(row["tip_hash"]),
            "valid": bool(row["valid"]),
            "error": row["error"],
            "input_count": int(row["input_count"]),
        }

    def verify_sources(self, batch_id: str) -> None:
        batch = self.get_batch(batch_id)
        maturity = int(batch["maturity"])
        rows = self.db.execute(
            """
            SELECT pcl.block_hash,pcl.worker,c.status,br.canonical,br.confirmations
            FROM payout_credit_links AS pcl
            JOIN credits AS c
              ON c.block_hash=pcl.block_hash AND c.worker=pcl.worker
            LEFT JOIN block_reconciliation AS br
              ON br.block_hash=pcl.block_hash
            WHERE pcl.batch_id=?
            ORDER BY pcl.block_hash,pcl.worker
            """,
            (batch_id,),
        ).fetchall()
        if not rows:
            raise RuntimeError("payout batch has no linked credits")
        for row in rows:
            if row["canonical"] is None or int(row["canonical"]) != 1:
                raise RuntimeError(f"source block is not canonical: {row['block_hash']}")
            if int(row["confirmations"]) < maturity:
                raise RuntimeError(
                    f"source block {row['block_hash']} has {row['confirmations']} confirmations; need {maturity}"
                )
            if str(row["status"]) != "planned":
                raise RuntimeError(
                    f"linked credit {row['block_hash']}:{row['worker']} is {row['status']}; expected planned"
                )

    def cancel_unbroadcast(self, batch_id: str) -> dict[str, Any]:
        payment = self.get_payment(batch_id)
        if payment is None:
            raise RuntimeError("unknown payment")
        if payment["state"] == "cancelled":
            return payment
        if payment["state"] != "psbt_ready" or payment["txid"] is not None:
            raise RuntimeError(
                f"only an unbroadcast psbt_ready payment can be cancelled; state={payment['state']}"
            )
        with self.db:
            links = self.db.execute(
                "SELECT block_hash,worker FROM payout_credit_links WHERE batch_id=? ORDER BY block_hash,worker",
                (batch_id,),
            ).fetchall()
            for link in links:
                rec = self.db.execute(
                    "SELECT canonical FROM block_reconciliation WHERE block_hash=?",
                    (link["block_hash"],),
                ).fetchone()
                status = "pending" if rec is not None and int(rec["canonical"]) == 1 else "orphaned"
                cur = self.db.execute(
                    "UPDATE credits SET status=? WHERE block_hash=? AND worker=? AND status='planned'",
                    (status, link["block_hash"], link["worker"]),
                )
                if cur.rowcount != 1:
                    existing = self.db.execute(
                        "SELECT status FROM credits WHERE block_hash=? AND worker=?",
                        (link["block_hash"], link["worker"]),
                    ).fetchone()
                    if existing is None or str(existing["status"]) != status:
                        raise RuntimeError("credit state changed before cancellation")
            self.db.execute(
                "UPDATE payout_transactions SET state='cancelled',last_error=NULL WHERE batch_id=?",
                (batch_id,),
            )
            self.db.execute(
                "UPDATE payout_batches SET state='cancelled' WHERE id=? AND state='psbt_ready'",
                (batch_id,),
            )
        result = self.get_payment(batch_id)
        assert result is not None
        return result


def decode_psbt(rpc: Any, psbt: str) -> dict[str, Any]:
    decoded = PAYTX.rpc_call(rpc, "decodepsbt", psbt)
    if not isinstance(decoded, dict):
        raise RuntimeError("decodepsbt returned no object")
    tx = decoded.get("tx")
    if not isinstance(tx, dict):
        raise RuntimeError("decodepsbt response has no transaction")
    return decoded


def psbt_outpoints(decoded: dict[str, Any]) -> list[dict[str, Any]]:
    tx = decoded.get("tx", {})
    vin = tx.get("vin", []) if isinstance(tx, dict) else []
    outpoints: list[dict[str, Any]] = []
    for item in vin:
        if not isinstance(item, dict):
            continue
        txid = item.get("txid")
        vout = item.get("vout")
        if isinstance(txid, str) and len(txid) == 64 and isinstance(vout, int) and vout >= 0:
            outpoints.append({"txid": txid.lower(), "vout": vout})
    if not outpoints:
        raise RuntimeError("funded PSBT has no spendable input outpoints")
    return outpoints


def preflight(
    ledger: GuardLedger,
    rpc: Any,
    batch_id: str,
    *,
    max_fee_sats: int | None = None,
) -> dict[str, Any]:
    payment = ledger.get_payment(batch_id)
    if payment is None:
        raise RuntimeError("build the CRAK-017 PSBT first")
    if payment["state"] != "psbt_ready" or payment["txid"] is not None:
        raise RuntimeError(f"preflight requires unbroadcast psbt_ready state; got {payment['state']}")
    if max_fee_sats is not None and max_fee_sats < 0:
        raise ValueError("max fee cannot be negative")

    tip_height, tip_hash, hashes = PAYOUT.chain_snapshot(rpc, ledger)
    ledger.reconcile_snapshot(tip_height, tip_hash, hashes)
    try:
        ledger.verify_sources(batch_id)
        fee_sats = payment.get("estimated_fee_sats")
        if max_fee_sats is not None:
            if fee_sats is None:
                raise RuntimeError("PSBT has no persisted fee estimate for max-fee enforcement")
            if int(fee_sats) > max_fee_sats:
                raise RuntimeError(f"estimated fee {fee_sats} sats exceeds max {max_fee_sats} sats")
        decoded = decode_psbt(rpc, str(payment["psbt"]))
        tx = decoded["tx"]
        PAYTX.verify_observed_outputs(ledger.get_batch(batch_id), tx)
        inputs = psbt_outpoints(decoded)
    except Exception as exc:
        ledger.record_preflight(batch_id, tip_height, tip_hash, False, error=str(exc))
        raise

    audit = ledger.record_preflight(
        batch_id,
        tip_height,
        tip_hash,
        True,
        input_count=len(inputs),
    )
    return {
        "batch_id": batch_id,
        "state": payment["state"],
        "estimated_fee_sats": payment.get("estimated_fee_sats"),
        "tip_height": tip_height,
        "tip_hash": tip_hash,
        "input_count": len(inputs),
        "preflight": audit,
        "safe_to_sign_and_broadcast_externally": True,
    }


def guarded_attach(
    ledger: GuardLedger,
    batch_id: str,
    txid: str,
    *,
    max_age_seconds: int,
) -> dict[str, Any]:
    if max_age_seconds < 1:
        raise ValueError("preflight max age must be positive")
    latest = ledger.latest_preflight(batch_id)
    if latest is None or not latest["valid"]:
        raise RuntimeError("no successful CRAK-018 preflight exists for this batch")
    age = time.time() - float(latest["checked_at"])
    if age > max_age_seconds:
        raise RuntimeError(
            f"latest successful preflight is stale ({int(age)}s old; max {max_age_seconds}s)"
        )
    return ledger.attach_txid(batch_id, txid)


def cancel(
    ledger: GuardLedger,
    rpc: Any,
    batch_id: str,
    wallet: str,
    *,
    confirm_not_broadcast: bool,
) -> dict[str, Any]:
    if not confirm_not_broadcast:
        raise RuntimeError(
            "refusing cancellation without --confirm-not-broadcast; verify the PSBT was never signed/broadcast"
        )
    payment = ledger.get_payment(batch_id)
    if payment is None:
        raise RuntimeError("unknown payment")
    if payment["state"] == "cancelled":
        return payment
    if payment["state"] != "psbt_ready" or payment["txid"] is not None:
        raise RuntimeError("cannot cancel a payment that may already be broadcast")

    tip_height, tip_hash, hashes = PAYOUT.chain_snapshot(rpc, ledger)
    ledger.reconcile_snapshot(tip_height, tip_hash, hashes)
    decoded = decode_psbt(rpc, str(payment["psbt"]))
    outpoints = psbt_outpoints(decoded)
    unlocked = PAYTX.rpc_call(rpc, "lockunspent", True, outpoints, wallet=wallet)
    if unlocked is not True:
        raise RuntimeError("wallet refused to unlock CRAK-017 PSBT inputs; ledger was not cancelled")
    return ledger.cancel_unbroadcast(batch_id)


def add_rpc_args(parser: argparse.ArgumentParser) -> None:
    PAYTX.add_rpc_args(parser)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit CRAK-018 payout preflight and recovery guard")
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("preflight", help="recheck sources, maturity, recipients and fee before external signing/broadcast")
    add_rpc_args(pre)
    pre.add_argument("--batch", required=True)
    pre.add_argument("--max-fee-sats", type=int)

    attach = sub.add_parser("guarded-attach", help="attach externally broadcast txid only after a fresh valid preflight")
    attach.add_argument("--batch", required=True)
    attach.add_argument("--txid", required=True)
    attach.add_argument("--preflight-max-age", type=int, default=900, help="seconds; default 900")

    can = sub.add_parser("cancel", help="unlock and cancel an unbroadcast PSBT after explicit operator attestation")
    add_rpc_args(can)
    can.add_argument("--batch", required=True)
    can.add_argument("--confirm-not-broadcast", action="store_true")

    status = sub.add_parser("status", help="show CRAK-017 payment plus latest CRAK-018 preflight")
    status.add_argument("--batch", required=True)

    args = parser.parse_args()
    ledger = GuardLedger(args.db)
    try:
        if args.command == "status":
            payment = ledger.get_payment(args.batch)
            if payment is None:
                raise RuntimeError("unknown payment")
            print(json.dumps({"payment": payment, "preflight": ledger.latest_preflight(args.batch)}, sort_keys=True, indent=2))
            return 0
        if args.command == "guarded-attach":
            result = guarded_attach(
                ledger,
                args.batch,
                args.txid,
                max_age_seconds=args.preflight_max_age,
            )
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0

        cli = BASE.resolve_executable(args.cli, "crakbit-cli", "crakbit-cli")
        rpc = BASE.Rpc(cli, args.network, args.datadir, args.rpcport)
        rpc.call("getblockcount")
        if args.command == "preflight":
            result = preflight(ledger, rpc, args.batch, max_fee_sats=args.max_fee_sats)
        elif args.command == "cancel":
            result = cancel(
                ledger,
                rpc,
                args.batch,
                args.wallet,
                confirm_not_broadcast=args.confirm_not_broadcast,
            )
        else:
            raise AssertionError("unhandled command")
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
