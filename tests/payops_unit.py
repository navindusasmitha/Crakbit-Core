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


accounting = load("crakpool_accounting_payops_test", ROOT / "scripts" / "crakpool-accounting.py")
payout = load("crakpool_payout_payops_test", ROOT / "scripts" / "crakpool-payout.py")
payops = load("crakpool_payops_unit", ROOT / "scripts" / "crakpool-payops.py")


def seed_db(db: Path) -> str:
    ledger = accounting.PoolLedger(db)
    ledger.register_worker("alice", Decimal(1))
    ledger.register_worker("bob", Decimal(1))
    ledger.record_share("alice", "job-1", Decimal(1), "01" * 32, False)
    end = ledger.record_share("bob", "job-1", Decimal(1), "02" * 32, True)
    credits = ledger.record_block_and_allocate("02" * 32, 1, 100, end, "proportional", 1000, 0)
    assert credits == {"alice": 50, "bob": 50}
    ledger.close()

    planner = payout.PayoutLedger(db)
    planner.register_address("alice", "crak1alice")
    planner.register_address("bob", "crak1bob")
    planner.reconcile_snapshot(100, "aa" * 32, {1: "02" * 32})
    batch = planner.create_plan(
        network="regtest",
        tip_height=100,
        tip_hash="aa" * 32,
        maturity=100,
        minimum_sats=1,
        max_outputs=10,
    )
    assert batch is not None
    batch_id = batch["id"]
    planner.close()
    return batch_id


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch_id = seed_db(db)
        ledger = payops.OpsLedger(db)

        planned = ledger.show_record(batch_id, now=1000)
        assert planned["state"] == "planned", planned
        assert planned["next_action"] == "build_psbt", planned

        payment = ledger.persist_psbt(batch_id, "cHNidP8BAFake", 123)
        assert payment["state"] == "psbt_ready"
        created = float(payment["created_at"])
        ready = ledger.show_record(batch_id, now=created + 10)
        assert ready["next_action"] == "run_preflight", ready
        stale_ready = ledger.show_record(batch_id, stale_seconds=3600, now=created + 4000)
        assert stale_ready["stale"] is True, stale_ready

        preflight = ledger.record_preflight(batch_id, 100, "aa" * 32, True, input_count=1)
        ready_after_preflight = ledger.show_record(
            batch_id,
            preflight_max_age=900,
            now=float(preflight["checked_at"]) + 10,
        )
        assert ready_after_preflight["next_action"] == "sign_broadcast_then_guarded_attach", ready_after_preflight
        expired_preflight = ledger.show_record(
            batch_id,
            preflight_max_age=900,
            now=float(preflight["checked_at"]) + 901,
        )
        assert expired_preflight["next_action"] == "run_preflight", expired_preflight

        txid = "ab" * 32
        attached = ledger.attach_txid(batch_id, txid)
        assert attached["state"] == "broadcast"
        broadcast = ledger.show_record(batch_id, now=float(attached["attached_at"]) + 10)
        assert broadcast["next_action"] == "refresh_confirmations", broadcast

        checked = ledger.record_check(batch_id, 2, 101)
        assert checked["state"] == "confirmed"
        recent = ledger.show_record(batch_id, stale_seconds=3600, now=float(checked["last_checked_at"]) + 10)
        assert recent["next_action"] == "wait_confirmations", recent
        stale = ledger.show_record(batch_id, stale_seconds=3600, now=float(checked["last_checked_at"]) + 4000)
        assert stale["next_action"] == "refresh_confirmations", stale
        assert stale["stale"] is True

        checked6 = ledger.record_check(batch_id, 6, 101)
        settle_ready = ledger.show_record(
            batch_id,
            required_confirmations=6,
            now=float(checked6["last_checked_at"]) + 10,
        )
        assert settle_ready["next_action"] == "settle", settle_ready

        paid = ledger.settle(batch_id, 6)
        assert paid["state"] == "paid"
        final = ledger.show_record(batch_id, now=float(checked6["last_checked_at"]) + 20)
        assert final["state"] == "paid", final
        assert final["next_action"] == "none", final
        assert final["stale"] is False

        summary = ledger.summary(now=float(checked6["last_checked_at"]) + 20)
        assert summary["batches"] == 1, summary
        assert summary["states"] == {"paid": 1}, summary
        assert summary["next_actions"] == {"none": 1}, summary
        assert summary["total_sats"] == 100, summary
        ledger.close()

    print("CRAK-019 payout operations monitor vectors: OK")


if __name__ == "__main__":
    main()
