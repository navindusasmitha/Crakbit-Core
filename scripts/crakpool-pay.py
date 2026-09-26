#!/usr/bin/env python3
"""CRAK-017 signed payout transaction pipeline.

Builds on CRAK-016 payout batches and deliberately separates money movement
into explicit prepare, broadcast and sync phases:

  planned -> prepared -> broadcast -> paid

A prepared transaction is fully signed and persisted, but is not broadcast.
Worker credit amounts are never reduced for transaction fees; the pool wallet
funds fees and change separately. Source-credit maturity/canonicality is checked
again immediately before broadcast. Restart recovery uses the persisted raw
transaction and txid.
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


def load_planner():
    here = Path(__file__).resolve().parent
    candidate = here / "crakpool-payout.py"
    if not candidate.exists():
        raise RuntimeError("CRAK-016 crakpool-payout.py not found beside crakpool-pay")
    spec = importlib.util.spec_from_file_location("crakpool_pay_planner", candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load CRAK-016 payout planner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PLANNER = load_planner()
BASE = PLANNER.BASE


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


def sats_to_coin_string(sats: int) -> str:
    if sats < 0:
        raise ValueError("negative satoshi amount")
    return f"{Decimal(sats) / COIN:.8f}"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def recipient_digest(outputs: list[tuple[str, int]]) -> str:
    return hashlib.sha256(canonical_json([[address, sats] for address, sats in outputs])).hexdigest()


def aggregate_outputs(batch: dict[str, Any]) -> list[tuple[str, int]]:
    grouped: dict[str, int] = {}
    for item in batch["outputs"]:
        address = str(item["address"])
        amount = int(item["amount_sats"])
        if amount <= 0:
            raise RuntimeError(f"non-positive payout amount for {item['worker']}")
        grouped[address] = grouped.get(address, 0) + amount
    outputs = sorted(grouped.items())
    if sum(amount for _, amount in outputs) != int(batch["total_sats"]):
        raise RuntimeError("aggregated payout outputs do not equal batch total")
    return outputs


def extract_non_change_outputs(decoded: dict[str, Any], changepos: int) -> list[tuple[str, int]]:
    tx = decoded.get("tx")
    if not isinstance(tx, dict) or not isinstance(tx.get("vout"), list):
        raise RuntimeError("decodepsbt response does not contain tx.vout")
    result: list[tuple[str, int]] = []
    for index, vout in enumerate(tx["vout"]):
        if index == changepos:
            continue
        if not isinstance(vout, dict):
            raise RuntimeError("invalid decoded transaction output")
        script = vout.get("scriptPubKey")
        if not isinstance(script, dict):
            raise RuntimeError("decoded output missing scriptPubKey")
        address = script.get("address")
        if not isinstance(address, str) or not address:
            raise RuntimeError("unexpected non-address output in payout transaction")
        result.append((address, coins_to_sats(vout.get("value"))))
    return sorted(result)


def extract_inputs(decoded_raw: dict[str, Any]) -> list[dict[str, Any]]:
    vin = decoded_raw.get("vin")
    if not isinstance(vin, list) or not vin:
        raise RuntimeError("signed payout transaction has no inputs")
    outpoints: list[dict[str, Any]] = []
    for item in vin:
        if not isinstance(item, dict) or not isinstance(item.get("txid"), str) or not isinstance(item.get("vout"), int):
            raise RuntimeError("signed payout transaction contains a non-standard input")
        outpoints.append({"txid": item["txid"], "vout": item["vout"]})
    return outpoints


def mempool_accept(rpc: Any, raw_hex: str) -> dict[str, Any]:
    result = rpc.call("testmempoolaccept", json.dumps([raw_hex], separators=(",", ":")))
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
        raise RuntimeError("unexpected testmempoolaccept response")
    return result[0]


def wallet_transaction(rpc: Any, wallet: str, txid: str) -> dict[str, Any] | None:
    # Confirm the wallet itself is reachable first so an unavailable wallet is
    # not silently treated as an unknown transaction.
    rpc.call("getwalletinfo", wallet=wallet)
    try:
        result = rpc.call("gettransaction", txid, wallet=wallet)
    except RuntimeError:
        return None
    return result if isinstance(result, dict) else None


def in_mempool(rpc: Any, txid: str) -> bool:
    try:
        result = rpc.call("getmempoolentry", txid)
    except RuntimeError:
        return False
    return isinstance(result, dict)


def set_input_locks(rpc: Any, wallet: str, outpoints: list[dict[str, Any]], *, unlock: bool) -> None:
    if not outpoints:
        return
    rpc.call(
        "lockunspent",
        "true" if unlock else "false",
        json.dumps(outpoints, separators=(",", ":")),
        wallet=wallet,
    )


class PaymentLedger(PLANNER.PayoutLedger):
    def __init__(self, path: str | Path):
        super().__init__(path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS payout_transactions (
                batch_id TEXT PRIMARY KEY,
                wallet TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                txid TEXT NOT NULL UNIQUE,
                raw_hex TEXT NOT NULL,
                fee_sats INTEGER NOT NULL,
                change_position INTEGER NOT NULL,
                recipient_digest TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                required_confirmations INTEGER NOT NULL,
                confirmations INTEGER NOT NULL DEFAULT 0,
                block_hash TEXT,
                broadcast_at REAL,
                paid_at REAL,
                last_error TEXT,
                FOREIGN KEY(batch_id) REFERENCES payout_batches(id)
            );
            CREATE INDEX IF NOT EXISTS payout_transactions_state
                ON payout_transactions(state);
            """
        )
        self.db.commit()

    def linked_credit_health(self, batch_id: str) -> dict[str, Any]:
        batch = self.db.execute(
            "SELECT maturity,state FROM payout_batches WHERE id=?", (batch_id,)
        ).fetchone()
        if batch is None:
            raise RuntimeError(f"unknown payout batch: {batch_id}")
        rows = self.db.execute(
            """
            SELECT pcl.block_hash,pcl.worker,c.status,br.canonical,br.confirmations
            FROM payout_credit_links pcl
            JOIN credits c ON c.block_hash=pcl.block_hash AND c.worker=pcl.worker
            LEFT JOIN block_reconciliation br ON br.block_hash=pcl.block_hash
            WHERE pcl.batch_id=?
            ORDER BY pcl.block_hash,pcl.worker
            """,
            (batch_id,),
        ).fetchall()
        if not rows:
            raise RuntimeError("payout batch has no linked credits")
        maturity = int(batch["maturity"])
        unhealthy: list[dict[str, Any]] = []
        for row in rows:
            canonical = row["canonical"] is not None and int(row["canonical"]) == 1
            confirmations = int(row["confirmations"]) if row["confirmations"] is not None else 0
            if not canonical or confirmations < maturity:
                unhealthy.append(
                    {
                        "block_hash": str(row["block_hash"]),
                        "worker": str(row["worker"]),
                        "status": str(row["status"]),
                        "canonical": canonical,
                        "confirmations": confirmations,
                    }
                )
        return {
            "batch_id": batch_id,
            "maturity": maturity,
            "credits": len(rows),
            "healthy": not unhealthy,
            "unhealthy": unhealthy,
        }

    def transaction(self, batch_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM payout_transactions WHERE batch_id=?", (batch_id,)).fetchone()
        if row is None:
            return None
        return {
            "batch_id": str(row["batch_id"]),
            "wallet": str(row["wallet"]),
            "state": str(row["state"]),
            "txid": str(row["txid"]),
            "fee_sats": int(row["fee_sats"]),
            "change_position": int(row["change_position"]),
            "recipient_digest": str(row["recipient_digest"]),
            "inputs": json.loads(str(row["inputs_json"])),
            "required_confirmations": int(row["required_confirmations"]),
            "confirmations": int(row["confirmations"]),
            "block_hash": str(row["block_hash"]) if row["block_hash"] is not None else None,
            "broadcast_at": float(row["broadcast_at"]) if row["broadcast_at"] is not None else None,
            "paid_at": float(row["paid_at"]) if row["paid_at"] is not None else None,
            "last_error": str(row["last_error"]) if row["last_error"] is not None else None,
            "raw_hex": str(row["raw_hex"]),
        }

    def persist_prepared(
        self,
        *,
        batch_id: str,
        wallet: str,
        txid: str,
        raw_hex: str,
        fee_sats: int,
        change_position: int,
        digest: str,
        inputs: list[dict[str, Any]],
        required_confirmations: int,
    ) -> dict[str, Any]:
        if fee_sats < 0 or required_confirmations < 1:
            raise ValueError("invalid prepared transaction metadata")
        now = time.time()
        with self.db:
            batch = self.db.execute("SELECT state FROM payout_batches WHERE id=?", (batch_id,)).fetchone()
            if batch is None:
                raise RuntimeError(f"unknown payout batch: {batch_id}")
            if str(batch["state"]) != "planned":
                raise RuntimeError(f"batch {batch_id} cannot be prepared from state {batch['state']}")
            if self.db.execute("SELECT 1 FROM payout_transactions WHERE batch_id=?", (batch_id,)).fetchone():
                raise RuntimeError(f"batch {batch_id} already has a payout transaction")

            links = int(
                self.db.execute(
                    "SELECT COUNT(*) AS n FROM payout_credit_links WHERE batch_id=?", (batch_id,)
                ).fetchone()["n"]
            )
            updated = self.db.execute(
                """
                UPDATE credits SET status='paying'
                WHERE status='planned' AND EXISTS (
                    SELECT 1 FROM payout_credit_links pcl
                    WHERE pcl.batch_id=? AND pcl.block_hash=credits.block_hash AND pcl.worker=credits.worker
                )
                """,
                (batch_id,),
            ).rowcount
            if updated != links:
                raise RuntimeError("linked credit state changed while reserving payout transaction")

            self.db.execute(
                """
                INSERT INTO payout_transactions(
                    batch_id,wallet,state,created_at,updated_at,txid,raw_hex,fee_sats,
                    change_position,recipient_digest,inputs_json,required_confirmations
                ) VALUES(?,?,'prepared',?,?,?,?,?,?,?,?,?)
                """,
                (
                    batch_id,
                    wallet,
                    now,
                    now,
                    txid,
                    raw_hex,
                    fee_sats,
                    change_position,
                    digest,
                    json.dumps(inputs, sort_keys=True, separators=(",", ":")),
                    required_confirmations,
                ),
            )
            self.db.execute("UPDATE payout_batches SET state='prepared' WHERE id=?", (batch_id,))
        tx = self.transaction(batch_id)
        assert tx is not None
        return tx

    def invalidate_prepared(self, batch_id: str, reason: str) -> dict[str, Any]:
        with self.db:
            tx = self.db.execute("SELECT state FROM payout_transactions WHERE batch_id=?", (batch_id,)).fetchone()
            if tx is None or str(tx["state"]) != "prepared":
                raise RuntimeError("only a prepared, unbroadcast payout can be invalidated")
            links = self.db.execute(
                "SELECT block_hash,worker FROM payout_credit_links WHERE batch_id=?", (batch_id,)
            ).fetchall()
            for link in links:
                rec = self.db.execute(
                    "SELECT canonical FROM block_reconciliation WHERE block_hash=?", (link["block_hash"],)
                ).fetchone()
                status = "pending" if rec is not None and int(rec["canonical"]) == 1 else "orphaned"
                self.db.execute(
                    "UPDATE credits SET status=? WHERE block_hash=? AND worker=? AND status='paying'",
                    (status, link["block_hash"], link["worker"]),
                )
            now = time.time()
            self.db.execute(
                "UPDATE payout_transactions SET state='invalidated',updated_at=?,last_error=? WHERE batch_id=?",
                (now, reason, batch_id),
            )
            self.db.execute("UPDATE payout_batches SET state='invalidated' WHERE id=?", (batch_id,))
        tx_data = self.transaction(batch_id)
        assert tx_data is not None
        return tx_data

    def mark_broadcast(self, batch_id: str) -> dict[str, Any]:
        now = time.time()
        with self.db:
            tx = self.db.execute("SELECT state FROM payout_transactions WHERE batch_id=?", (batch_id,)).fetchone()
            if tx is None:
                raise RuntimeError(f"batch {batch_id} has no prepared transaction")
            state = str(tx["state"])
            if state not in {"prepared", "broadcast"}:
                raise RuntimeError(f"transaction cannot enter broadcast from state {state}")
            self.db.execute(
                """
                UPDATE payout_transactions
                SET state='broadcast',updated_at=?,broadcast_at=COALESCE(broadcast_at,?),last_error=NULL
                WHERE batch_id=?
                """,
                (now, now, batch_id),
            )
            self.db.execute("UPDATE payout_batches SET state='broadcast' WHERE id=?", (batch_id,))
        tx_data = self.transaction(batch_id)
        assert tx_data is not None
        return tx_data

    def update_seen(self, batch_id: str, confirmations: int, block_hash: str | None) -> dict[str, Any]:
        with self.db:
            self.db.execute(
                """
                UPDATE payout_transactions
                SET confirmations=?,block_hash=?,updated_at=?,last_error=NULL
                WHERE batch_id=?
                """,
                (confirmations, block_hash, time.time(), batch_id),
            )
        tx_data = self.transaction(batch_id)
        assert tx_data is not None
        return tx_data

    def mark_paid(self, batch_id: str, confirmations: int, block_hash: str | None) -> dict[str, Any]:
        now = time.time()
        with self.db:
            tx = self.db.execute(
                "SELECT state,required_confirmations FROM payout_transactions WHERE batch_id=?", (batch_id,)
            ).fetchone()
            if tx is None:
                raise RuntimeError(f"batch {batch_id} has no transaction")
            if confirmations < int(tx["required_confirmations"]):
                raise RuntimeError("transaction has not reached the required confirmations")
            links = int(
                self.db.execute(
                    "SELECT COUNT(*) AS n FROM payout_credit_links WHERE batch_id=?", (batch_id,)
                ).fetchone()["n"]
            )
            updated = self.db.execute(
                """
                UPDATE credits SET status='paid'
                WHERE status='paying' AND EXISTS (
                    SELECT 1 FROM payout_credit_links pcl
                    WHERE pcl.batch_id=? AND pcl.block_hash=credits.block_hash AND pcl.worker=credits.worker
                )
                """,
                (batch_id,),
            ).rowcount
            if updated != links:
                raise RuntimeError("not all reserved credits are available for paid finalization")
            self.db.execute(
                """
                UPDATE payout_transactions
                SET state='paid',confirmations=?,block_hash=?,updated_at=?,paid_at=?,last_error=NULL
                WHERE batch_id=?
                """,
                (confirmations, block_hash, now, now, batch_id),
            )
            self.db.execute("UPDATE payout_batches SET state='paid' WHERE id=?", (batch_id,))
        tx_data = self.transaction(batch_id)
        assert tx_data is not None
        return tx_data

    def mark_conflicted(self, batch_id: str, confirmations: int, reason: str) -> dict[str, Any]:
        with self.db:
            self.db.execute(
                """
                UPDATE payout_transactions
                SET state='conflicted',confirmations=?,updated_at=?,last_error=?
                WHERE batch_id=?
                """,
                (confirmations, time.time(), reason, batch_id),
            )
            self.db.execute("UPDATE payout_batches SET state='payment_conflict' WHERE id=?", (batch_id,))
        tx_data = self.transaction(batch_id)
        assert tx_data is not None
        return tx_data

    def note_error(self, batch_id: str, reason: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE payout_transactions SET updated_at=?,last_error=? WHERE batch_id=?",
                (time.time(), reason, batch_id),
            )

    def payment_status(self) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT state,COUNT(*) AS n,COALESCE(SUM(fee_sats),0) AS fees FROM payout_transactions GROUP BY state ORDER BY state"
        ).fetchall()
        return {
            "transactions": {
                str(row["state"]): {"count": int(row["n"]), "fee_sats": int(row["fees"])}
                for row in rows
            }
        }


def verify_batch_network(batch: dict[str, Any], network: str) -> None:
    if str(batch["network"]) != network:
        raise RuntimeError(f"batch network {batch['network']} does not match selected network {network}")


def prepare_transaction(
    ledger: PaymentLedger,
    rpc: Any,
    *,
    batch_id: str,
    wallet: str,
    network: str,
    fee_rate: Decimal,
    max_fee_sats: int,
    required_confirmations: int,
) -> dict[str, Any]:
    if not fee_rate.is_finite() or fee_rate <= 0:
        raise ValueError("fee rate must be positive")
    if max_fee_sats < 1:
        raise ValueError("max fee must be positive")
    if required_confirmations < 1:
        raise ValueError("required confirmations must be positive")
    if ledger.transaction(batch_id) is not None:
        raise RuntimeError(f"batch {batch_id} already has a payout transaction")

    tip_height, tip_hash, hashes = PLANNER.chain_snapshot(rpc, ledger)
    ledger.reconcile_snapshot(tip_height, tip_hash, hashes)
    batch = ledger.get_batch(batch_id)
    verify_batch_network(batch, network)
    if batch["state"] != "planned":
        raise RuntimeError(f"batch {batch_id} is not payable from state {batch['state']}")
    health = ledger.linked_credit_health(batch_id)
    if not health["healthy"]:
        raise RuntimeError("payout source credits are not canonical and mature")

    rpc.call("getwalletinfo", wallet=wallet)
    expected = aggregate_outputs(batch)
    for address, _ in expected:
        info = rpc.call("validateaddress", address)
        if not isinstance(info, dict) or not info.get("isvalid"):
            raise RuntimeError(f"batch contains invalid payout address for {network}: {address}")

    outputs_arg = [{address: sats_to_coin_string(amount)} for address, amount in expected]
    options = {
        "add_inputs": True,
        "include_unsafe": False,
        "minconf": 1,
        "lockUnspents": True,
        "replaceable": False,
        "fee_rate": str(fee_rate),
    }
    funded = rpc.call(
        "walletcreatefundedpsbt",
        "[]",
        json.dumps(outputs_arg, separators=(",", ":")),
        "0",
        json.dumps(options, separators=(",", ":")),
        "true",
        wallet=wallet,
    )
    if not isinstance(funded, dict) or not isinstance(funded.get("psbt"), str):
        raise RuntimeError("walletcreatefundedpsbt returned an invalid response")

    locked_inputs: list[dict[str, Any]] = []
    try:
        fee_sats = coins_to_sats(funded.get("fee"))
        changepos = int(funded.get("changepos", -1))
        if fee_sats > max_fee_sats:
            raise RuntimeError(f"funded payout fee {fee_sats} exceeds max {max_fee_sats} sats")

        decoded_psbt = rpc.call("decodepsbt", funded["psbt"])
        if not isinstance(decoded_psbt, dict):
            raise RuntimeError("decodepsbt returned an invalid response")
        actual = extract_non_change_outputs(decoded_psbt, changepos)
        if actual != expected:
            raise RuntimeError(f"funded payout recipients changed: expected={expected} actual={actual}")

        processed = rpc.call("walletprocesspsbt", funded["psbt"], wallet=wallet)
        if not isinstance(processed, dict) or not processed.get("complete") or not isinstance(processed.get("psbt"), str):
            raise RuntimeError("pool wallet did not fully sign the payout PSBT")
        finalized = rpc.call("finalizepsbt", processed["psbt"])
        if not isinstance(finalized, dict) or not finalized.get("complete") or not isinstance(finalized.get("hex"), str):
            raise RuntimeError("signed payout PSBT could not be finalized")
        raw_hex = str(finalized["hex"])
        decoded_raw = rpc.call("decoderawtransaction", raw_hex)
        if not isinstance(decoded_raw, dict) or not isinstance(decoded_raw.get("txid"), str):
            raise RuntimeError("decoderawtransaction did not return a txid")
        txid = str(decoded_raw["txid"])
        locked_inputs = extract_inputs(decoded_raw)

        acceptance = mempool_accept(rpc, raw_hex)
        if not acceptance.get("allowed"):
            reason = acceptance.get("reject-reason") or acceptance.get("package-error") or "rejected"
            raise RuntimeError(f"prepared payout fails mempool policy: {reason}")

        tx = ledger.persist_prepared(
            batch_id=batch_id,
            wallet=wallet,
            txid=txid,
            raw_hex=raw_hex,
            fee_sats=fee_sats,
            change_position=changepos,
            digest=recipient_digest(expected),
            inputs=locked_inputs,
            required_confirmations=required_confirmations,
        )
        return {
            "batch": ledger.get_batch(batch_id),
            "transaction": {k: v for k, v in tx.items() if k != "raw_hex"},
            "mempool_policy": acceptance,
            "broadcast": False,
        }
    except Exception:
        # walletcreatefundedpsbt(lockUnspents=true) can leave selected coins
        # locked if a later verification/signing step fails. Release only the
        # inputs we can prove belong to this failed preparation.
        if locked_inputs:
            try:
                set_input_locks(rpc, wallet, locked_inputs, unlock=True)
            except Exception:
                pass
        raise


def broadcast_transaction(
    ledger: PaymentLedger,
    rpc: Any,
    *,
    batch_id: str,
    network: str,
) -> dict[str, Any]:
    tx = ledger.transaction(batch_id)
    if tx is None:
        raise RuntimeError(f"batch {batch_id} has no prepared transaction")
    batch = ledger.get_batch(batch_id)
    verify_batch_network(batch, network)
    if tx["state"] == "paid":
        return {"batch": batch, "transaction": {k: v for k, v in tx.items() if k != "raw_hex"}, "already_paid": True}
    if tx["state"] == "broadcast":
        return {"batch": batch, "transaction": {k: v for k, v in tx.items() if k != "raw_hex"}, "already_broadcast": True}
    if tx["state"] != "prepared":
        raise RuntimeError(f"transaction cannot broadcast from state {tx['state']}")

    tip_height, tip_hash, hashes = PLANNER.chain_snapshot(rpc, ledger)
    ledger.reconcile_snapshot(tip_height, tip_hash, hashes)
    health = ledger.linked_credit_health(batch_id)
    if not health["healthy"]:
        invalid = ledger.invalidate_prepared(batch_id, "source credit lost canonical maturity before broadcast")
        try:
            set_input_locks(rpc, tx["wallet"], tx["inputs"], unlock=True)
        except Exception:
            pass
        raise RuntimeError(f"payout invalidated before broadcast: {invalid['last_error']}")

    known = wallet_transaction(rpc, tx["wallet"], tx["txid"])
    if known is not None or in_mempool(rpc, tx["txid"]):
        marked = ledger.mark_broadcast(batch_id)
        return {
            "batch": ledger.get_batch(batch_id),
            "transaction": {k: v for k, v in marked.items() if k != "raw_hex"},
            "recovered_after_prior_broadcast": True,
        }

    acceptance = mempool_accept(rpc, tx["raw_hex"])
    if not acceptance.get("allowed"):
        reason = acceptance.get("reject-reason") or acceptance.get("package-error") or "rejected"
        ledger.note_error(batch_id, f"pre-broadcast mempool rejection: {reason}")
        raise RuntimeError(f"prepared payout no longer passes mempool policy: {reason}")

    sent_txid = str(rpc.call("sendrawtransaction", tx["raw_hex"], parse_json=False)).strip()
    if sent_txid != tx["txid"]:
        raise RuntimeError(f"sendrawtransaction returned unexpected txid {sent_txid}")
    marked = ledger.mark_broadcast(batch_id)
    try:
        set_input_locks(rpc, tx["wallet"], tx["inputs"], unlock=True)
    except Exception:
        # The transaction is already broadcast; an unlock failure is not a
        # reason to roll back database state. Spent inputs cannot be selected.
        pass
    return {
        "batch": ledger.get_batch(batch_id),
        "transaction": {k: v for k, v in marked.items() if k != "raw_hex"},
        "mempool_policy": acceptance,
        "broadcast": True,
    }


def sync_one(ledger: PaymentLedger, rpc: Any, batch_id: str, *, rebroadcast: bool) -> dict[str, Any]:
    tx = ledger.transaction(batch_id)
    if tx is None:
        raise RuntimeError(f"batch {batch_id} has no payout transaction")
    state = tx["state"]
    if state in {"invalidated", "conflicted"}:
        return {"batch_id": batch_id, "state": state, "action": "manual-review", "last_error": tx["last_error"]}

    info = wallet_transaction(rpc, tx["wallet"], tx["txid"])
    if info is not None:
        confirmations = int(info.get("confirmations", 0))
        block_hash = info.get("blockhash") if isinstance(info.get("blockhash"), str) else None
        if confirmations < 0:
            marked = ledger.mark_conflicted(batch_id, confirmations, "wallet reports a conflicted payout transaction")
            return {"batch_id": batch_id, "state": marked["state"], "confirmations": confirmations, "action": "manual-review"}
        if state == "prepared":
            tx = ledger.mark_broadcast(batch_id)
            state = tx["state"]
        ledger.update_seen(batch_id, confirmations, block_hash)
        if confirmations >= int(tx["required_confirmations"]) and state != "paid":
            paid = ledger.mark_paid(batch_id, confirmations, block_hash)
            return {"batch_id": batch_id, "state": "paid", "confirmations": confirmations, "txid": paid["txid"], "action": "finalized"}
        return {"batch_id": batch_id, "state": state, "confirmations": confirmations, "txid": tx["txid"], "action": "observed"}

    if in_mempool(rpc, tx["txid"]):
        if state == "prepared":
            tx = ledger.mark_broadcast(batch_id)
        ledger.update_seen(batch_id, 0, None)
        return {"batch_id": batch_id, "state": "broadcast", "confirmations": 0, "txid": tx["txid"], "action": "recovered-mempool"}

    acceptance = mempool_accept(rpc, tx["raw_hex"])
    if acceptance.get("allowed"):
        if state == "prepared":
            # Re-establish wallet locks after a node restart. The persisted raw
            # transaction remains the authority; no new transaction is built.
            try:
                set_input_locks(rpc, tx["wallet"], tx["inputs"], unlock=False)
            except Exception as exc:
                ledger.note_error(batch_id, f"unable to restore prepared input locks: {exc}")
        if state == "broadcast" and rebroadcast:
            sent = str(rpc.call("sendrawtransaction", tx["raw_hex"], parse_json=False)).strip()
            if sent != tx["txid"]:
                raise RuntimeError(f"rebroadcast returned unexpected txid {sent}")
            ledger.note_error(batch_id, "")
            return {"batch_id": batch_id, "state": "broadcast", "confirmations": 0, "txid": tx["txid"], "action": "rebroadcast"}
        reason = "prepared transaction is valid and awaiting explicit broadcast" if state == "prepared" else "broadcast transaction is no longer known; rebroadcast available"
        ledger.note_error(batch_id, reason)
        return {"batch_id": batch_id, "state": state, "confirmations": 0, "txid": tx["txid"], "action": "ready", "rebroadcast_available": state == "broadcast"}

    reason = str(acceptance.get("reject-reason") or acceptance.get("package-error") or "transaction unavailable")
    ledger.note_error(batch_id, reason)
    return {"batch_id": batch_id, "state": state, "txid": tx["txid"], "action": "manual-review", "reason": reason}


def add_rpc_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--network", choices=["testnet4", "regtest"], default="testnet4")
    parser.add_argument("--datadir", default=os.environ.get("CRAKBIT_DATADIR", str(Path.home() / ".crakbit")))
    parser.add_argument("--rpcport", type=int)
    parser.add_argument("--cli")


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit CRAK-017 signed payout pipeline")
    parser.add_argument("--db", required=True, help="CRAK-015/016 SQLite accounting database")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="fund, sign, verify and persist a payout transaction without broadcasting")
    add_rpc_args(prepare)
    prepare.add_argument("--batch", required=True)
    prepare.add_argument("--wallet", required=True)
    prepare.add_argument("--fee-rate", default="1.0", help="fee rate in sat/vB")
    prepare.add_argument("--max-fee-sats", type=int, default=1_000_000)
    prepare.add_argument("--confirmations", type=int, default=6, help="confirmations required before credits become paid")

    broadcast = sub.add_parser("broadcast", help="reconcile source credits and broadcast one prepared transaction")
    add_rpc_args(broadcast)
    broadcast.add_argument("--batch", required=True)

    sync = sub.add_parser("sync", help="recover and advance persisted payout transactions from node/wallet state")
    add_rpc_args(sync)
    sync.add_argument("--batch", help="sync one batch; default syncs all transactions")
    sync.add_argument("--rebroadcast", action="store_true", help="rebroadcast missing broadcast-state raw transactions")

    show = sub.add_parser("show", help="show persisted transaction metadata")
    show.add_argument("--batch", required=True)
    sub.add_parser("status", help="show CRAK-017 payment state counts")
    args = parser.parse_args()

    ledger = PaymentLedger(args.db)
    try:
        if args.command == "show":
            tx = ledger.transaction(args.batch)
            if tx is None:
                raise RuntimeError(f"batch {args.batch} has no payout transaction")
            tx = {k: v for k, v in tx.items() if k != "raw_hex"}
            print(json.dumps({"batch": ledger.get_batch(args.batch), "transaction": tx}, sort_keys=True, indent=2))
            return 0
        if args.command == "status":
            out = ledger.status()
            out.update(ledger.payment_status())
            print(json.dumps(out, sort_keys=True, indent=2))
            return 0

        cli = BASE.resolve_executable(args.cli, "crakbit-cli", "crakbit-cli")
        rpc = BASE.Rpc(cli, args.network, args.datadir, args.rpcport)
        rpc.call("getblockcount")

        if args.command == "prepare":
            try:
                fee_rate = Decimal(str(args.fee_rate))
            except InvalidOperation as exc:
                raise ValueError("invalid --fee-rate") from exc
            result = prepare_transaction(
                ledger,
                rpc,
                batch_id=args.batch,
                wallet=args.wallet,
                network=args.network,
                fee_rate=fee_rate,
                max_fee_sats=args.max_fee_sats,
                required_confirmations=args.confirmations,
            )
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0

        if args.command == "broadcast":
            result = broadcast_transaction(ledger, rpc, batch_id=args.batch, network=args.network)
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0

        if args.command == "sync":
            if args.batch:
                batch_ids = [args.batch]
            else:
                batch_ids = [
                    str(row["batch_id"])
                    for row in ledger.db.execute(
                        "SELECT batch_id FROM payout_transactions ORDER BY created_at,batch_id"
                    ).fetchall()
                ]
            results = [sync_one(ledger, rpc, batch_id, rebroadcast=args.rebroadcast) for batch_id in batch_ids]
            print(json.dumps({"results": results}, sort_keys=True, indent=2))
            return 0
        raise RuntimeError(f"unknown command: {args.command}")
    finally:
        ledger.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, sqlite3.Error) as exc:
        print(f"crakpool-pay: {exc}", file=sys.stderr)
        raise SystemExit(1)
