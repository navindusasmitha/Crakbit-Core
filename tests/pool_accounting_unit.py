#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "crakpool-accounting.py"
spec = importlib.util.spec_from_file_location("crakpool_accounting_unit", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load CRAK-015 accounting module")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def main() -> None:
    # Deterministic satoshi conservation / remainder ordering.
    assert mod.allocate_satoshis({"a": Decimal(1), "b": Decimal(3)}, 100) == {"a": 25, "b": 75}
    assert mod.allocate_satoshis({"a": Decimal(1), "b": Decimal(1)}, 1) == {"a": 1, "b": 0}

    # Vardiff reacts in the expected direction and obeys the 4x/0.25x clamps.
    assert mod.next_vardiff(Decimal(1), 5.0, 20.0, Decimal("0.01"), Decimal(100)) == Decimal(4)
    assert mod.next_vardiff(Decimal(1), 80.0, 20.0, Decimal("0.01"), Decimal(100)) == Decimal("0.25")
    assert mod.next_vardiff(Decimal(1), 20.0, 20.0, Decimal("0.01"), Decimal(100)) == Decimal(1)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pool.sqlite3"
        ledger = mod.PoolLedger(path)
        assert ledger.register_worker("alice", Decimal(1)) == Decimal(1)
        assert ledger.register_worker("bob", Decimal(3)) == Decimal(3)
        s1 = ledger.record_share("alice", "job-1", Decimal(1), "01" * 32, False)
        s2 = ledger.record_share("bob", "job-1", Decimal(3), "02" * 32, True)
        assert (s1, s2) == (1, 2)
        credits = ledger.record_block_and_allocate(
            "02" * 32,
            1,
            100,
            s2,
            "proportional",
            1000,
            0,
        )
        assert credits == {"alice": 25, "bob": 75}

        # Proportional rounds restart after the previous found block.
        s3 = ledger.record_share("alice", "job-2", Decimal(2), "03" * 32, True)
        credits2 = ledger.record_block_and_allocate(
            "03" * 32,
            2,
            50,
            s3,
            "proportional",
            1000,
            0,
        )
        assert credits2 == {"alice": 50}
        stats = ledger.stats(600)
        assert stats["blocks"] == 2
        assert stats["reward_sats"] == 150
        assert stats["pending_sats"] == 150
        alice = next(item for item in stats["workers"] if item["worker"] == "alice")
        assert alice["accepted_shares"] == 2
        assert alice["estimated_hashrate_hs"] > 0
        ledger.close()

        # Re-open to prove the ledger survives a pool process restart.
        reopened = mod.PoolLedger(path)
        assert reopened.stats(600)["pending_sats"] == 150
        reopened.close()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pplns.sqlite3"
        ledger = mod.PoolLedger(path)
        ledger.register_worker("alice", Decimal(1))
        ledger.register_worker("bob", Decimal(1))
        ledger.record_share("alice", "job-a", Decimal(1), "11" * 32, False)
        ledger.record_share("bob", "job-a", Decimal(1), "12" * 32, False)
        end = ledger.record_share("alice", "job-a", Decimal(1), "13" * 32, True)
        # PPLNS window=2 selects bob + alice; 10% accounting fee leaves 90 sats.
        credits = ledger.record_block_and_allocate(
            "13" * 32,
            1,
            100,
            end,
            "pplns",
            2,
            1000,
        )
        assert credits == {"alice": 45, "bob": 45}
        stats = ledger.stats(600)
        assert stats["pool_fee_sats"] == 10
        assert stats["credited_sats"] == 90
        assert stats["pending_sats"] == 90
        ledger.close()

    print("CRAK-015 accounting/vardiff unit vectors: OK")


if __name__ == "__main__":
    main()
