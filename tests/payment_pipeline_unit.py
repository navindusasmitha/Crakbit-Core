#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


accounting = load("crakpool_accounting_for_payment_test", ROOT / "scripts" / "crakpool-accounting.py")
planner_mod = load("crakpool_payout_for_payment_test", ROOT / "scripts" / "crakpool-payout.py")
pay = load("crakpool_pay_unit", ROOT / "scripts" / "crakpool-pay.py")


def build_batch(db: Path, block_hash: str = "02" * 32):
    ledger = accounting.PoolLedger(db)
    ledger.register_worker("alice", Decimal(1))
    ledger.register_worker("bob", Decimal(3))
    ledger.record_share("alice", "job-1", Decimal(1), "01" * 32, False)
    end = ledger.record_share("bob", "job-1", Decimal(3), block_hash, True)
    credits = ledger.record_block_and_allocate(block_hash, 1, 100, end, "proportional", 1000, 0)
    assert credits == {"alice": 25, "bob": 75}
    ledger.close()

    planner = planner_mod.PayoutLedger(db)
    planner.register_address("alice", "rcrak1shared")
    planner.register_address("bob", "rcrak1shared")
    planner.reconcile_snapshot(100, "aa" * 32, {1: block_hash})
    batch = planner.create_plan(
        network="regtest",
        tip_height=100,
        tip_hash="aa" * 32,
        maturity=100,
        minimum_sats=1,
        max_outputs=10,
    )
    assert batch is not None
    planner.close()
    return batch


def main() -> None:
    assert pay.sats_to_coin_string(125_000_000) == "1.25000000"
    assert pay.coins_to_sats("1.25000000") == 125_000_000

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch = build_batch(db)
        # Two workers may intentionally share one payout address. On-chain the
        # transaction must aggregate it while the ledger retains worker detail.
        assert pay.aggregate_outputs(batch) == [("rcrak1shared", 100)]

        ledger = pay.PaymentLedger(db)
        health = ledger.linked_credit_health(batch["id"])
        assert health["healthy"] is True
        tx = ledger.persist_prepared(
            batch_id=batch["id"],
            wallet="pool",
            txid="11" * 32,
            raw_hex="00",
            fee_sats=7,
            change_position=1,
            digest=pay.recipient_digest([("rcrak1shared", 100)]),
            inputs=[{"txid": "22" * 32, "vout": 0}],
            required_confirmations=6,
        )
        assert tx["state"] == "prepared"
        assert ledger.get_batch(batch["id"])["state"] == "prepared"
        status = ledger.status()
        assert status["credits"]["paying"]["sats"] == 100

        tx = ledger.mark_broadcast(batch["id"])
        assert tx["state"] == "broadcast"
        ledger.update_seen(batch["id"], 5, None)
        assert ledger.transaction(batch["id"])["confirmations"] == 5
        paid = ledger.mark_paid(batch["id"], 6, "33" * 32)
        assert paid["state"] == "paid"
        assert ledger.get_batch(batch["id"])["state"] == "paid"
        status = ledger.status()
        assert status["credits"]["paid"]["sats"] == 100
        assert ledger.payment_status()["transactions"]["paid"]["count"] == 1
        ledger.close()

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch = build_batch(db, "04" * 32)
        ledger = pay.PaymentLedger(db)
        ledger.persist_prepared(
            batch_id=batch["id"],
            wallet="pool",
            txid="44" * 32,
            raw_hex="00",
            fee_sats=8,
            change_position=-1,
            digest=pay.recipient_digest([("rcrak1shared", 100)]),
            inputs=[{"txid": "55" * 32, "vout": 1}],
            required_confirmations=1,
        )

        # CRAK-016 reconciliation no longer rewrites paying credits. CRAK-017
        # sees the source reorg and explicitly invalidates only the unbroadcast
        # transaction, releasing credits according to canonicality.
        ledger.reconcile_snapshot(100, "bb" * 32, {1: "ff" * 32})
        assert ledger.linked_credit_health(batch["id"])["healthy"] is False
        invalid = ledger.invalidate_prepared(batch["id"], "unit source reorg")
        assert invalid["state"] == "invalidated"
        assert ledger.get_batch(batch["id"])["state"] == "invalidated"
        assert ledger.status()["credits"]["orphaned"]["sats"] == 100
        ledger.close()

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch = build_batch(db, "06" * 32)
        ledger = pay.PaymentLedger(db)
        ledger.persist_prepared(
            batch_id=batch["id"],
            wallet="pool",
            txid="66" * 32,
            raw_hex="00",
            fee_sats=9,
            change_position=-1,
            digest=pay.recipient_digest([("rcrak1shared", 100)]),
            inputs=[{"txid": "77" * 32, "vout": 2}],
            required_confirmations=1,
        )
        ledger.mark_broadcast(batch["id"])
        conflicted = ledger.mark_conflicted(batch["id"], -1, "unit conflict")
        assert conflicted["state"] == "conflicted"
        assert ledger.get_batch(batch["id"])["state"] == "payment_conflict"
        # Reserved credits are intentionally not released after a broadcast
        # conflict, preventing an automatic duplicate payout.
        assert ledger.status()["credits"]["paying"]["sats"] == 100
        ledger.close()

    print("CRAK-017 signed payout state-machine vectors: OK")


if __name__ == "__main__":
    main()
