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


accounting = load("crakpool_accounting_for_payout_test", ROOT / "scripts" / "crakpool-accounting.py")
payout = load("crakpool_payout_unit", ROOT / "scripts" / "crakpool-payout.py")


def main() -> None:
    assert payout.coins_to_sats("1.25000000") == 125_000_000

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        ledger = accounting.PoolLedger(db)
        ledger.register_worker("alice", Decimal(1))
        ledger.register_worker("bob", Decimal(3))
        ledger.record_share("alice", "job-1", Decimal(1), "01" * 32, False)
        end = ledger.record_share("bob", "job-1", Decimal(3), "02" * 32, True)
        credits = ledger.record_block_and_allocate(
            "02" * 32,
            1,
            100,
            end,
            "proportional",
            1000,
            0,
        )
        assert credits == {"alice": 25, "bob": 75}
        ledger.close()

        planner = payout.PayoutLedger(db)
        planner.register_address("alice", "crak1alice")
        planner.register_address("bob", "crak1bob")

        # 99 confirmations is intentionally not enough for a 100-block maturity.
        snap = planner.reconcile_snapshot(99, "aa" * 32, {1: "02" * 32})
        assert snap["canonical_blocks"] == 1
        assert planner.create_plan(
            network="regtest",
            tip_height=99,
            tip_hash="aa" * 32,
            maturity=100,
            minimum_sats=1,
            max_outputs=10,
        ) is None

        # At 100 confirmations the complete 100 sats become plan-eligible.
        planner.reconcile_snapshot(100, "bb" * 32, {1: "02" * 32})
        batch = planner.create_plan(
            network="regtest",
            tip_height=100,
            tip_hash="bb" * 32,
            maturity=100,
            minimum_sats=1,
            max_outputs=10,
            funding_checked=True,
            wallet_trusted_sats=1_000,
            fee_reserve_sats=10,
        )
        assert batch is not None
        assert batch["state"] == "planned"
        assert batch["total_sats"] == 100
        assert batch["output_count"] == 2
        assert [item["worker"] for item in batch["outputs"]] == ["alice", "bob"]
        first_id = batch["id"]
        status = planner.status()
        assert status["credits"]["planned"]["sats"] == 100

        # A reorg that removes the credited block invalidates the unbroadcast batch
        # and makes those credits unspendable/orphaned.
        reorg = planner.reconcile_snapshot(100, "cc" * 32, {1: "ff" * 32})
        assert reorg["orphaned_blocks"] == 1
        assert first_id in reorg["invalidated_batches"]
        assert planner.get_batch(first_id)["state"] == "invalidated"
        assert planner.status()["credits"]["orphaned"]["sats"] == 100

        # If a later chain snapshot contains the block again, credits recover to
        # pending but the old invalidated plan is never silently reactivated.
        planner.reconcile_snapshot(101, "dd" * 32, {1: "02" * 32})
        assert planner.status()["credits"]["pending"]["sats"] == 100
        second = planner.create_plan(
            network="regtest",
            tip_height=101,
            tip_hash="dd" * 32,
            maturity=100,
            minimum_sats=1,
            max_outputs=10,
        )
        assert second is not None
        assert second["id"] != first_id
        cancelled = planner.cancel_batch(second["id"])
        assert cancelled["state"] == "cancelled"
        assert planner.status()["credits"]["pending"]["sats"] == 100
        planner.close()

    print("CRAK-016 reconciliation/payout planner unit vectors: OK")


if __name__ == "__main__":
    main()
