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


accounting = load("crakpool_accounting_paytx_test", ROOT / "scripts" / "crakpool-accounting.py")
payout = load("crakpool_payout_paytx_test", ROOT / "scripts" / "crakpool-payout.py")
paytx = load("crakpool_paytx_unit", ROOT / "scripts" / "crakpool-paytx.py")


class FakeRpc:
    def __init__(self):
        self.calls = []

    def call(self, method, *params, wallet=None, parse_json=True):
        self.calls.append((method, params, wallet, parse_json))
        if method == "getblockcount":
            return 100
        if method == "getblockhash":
            height = int(params[0])
            if height == 100:
                return "aa" * 32
            if height == 1:
                return "02" * 32
            return f"{height:064x}"[-64:]
        if method == "walletcreatefundedpsbt":
            assert wallet == "poolwallet"
            assert params[0] == "[]"
            assert 'crak1alice' in params[1]
            assert 'crak1bob' in params[1]
            assert '"lock_unspents":true' in params[3]
            return {"psbt": "cHNidP8BAFake", "fee": 0.00000123, "changepos": 2}
        if method == "gettransaction":
            assert wallet == "poolwallet"
            return {"confirmations": 6, "blockhash": "bb" * 32, "hex": "deadbeef"}
        if method == "decoderawtransaction":
            assert params[0] == "deadbeef"
            return {
                "vout": [
                    {"value": 0.00000050, "scriptPubKey": {"address": "crak1alice"}},
                    {"value": 0.00000050, "scriptPubKey": {"address": "crak1bob"}},
                    {"value": 1.0, "scriptPubKey": {"address": "rcrak1change"}},
                ]
            }
        if method == "getblockheader":
            return {"height": 106}
        raise AssertionError(f"unexpected RPC {method} {params}")


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
    assert paytx.sats_to_coins(123456789) == "1.23456789"

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch_id = seed_db(db)
        rpc = FakeRpc()
        ledger = paytx.PaymentLedger(db)

        built = paytx.build_psbt(ledger, rpc, batch_id, "poolwallet", Decimal("1.5"))
        assert built["state"] == "psbt_ready", built
        assert built["txid"] is None, built
        assert built["estimated_fee_sats"] == 123, built
        assert ledger.get_batch(batch_id)["state"] == "psbt_ready"

        # Re-running build is idempotent and cannot silently create a second PSBT.
        again = paytx.build_psbt(ledger, rpc, batch_id, "poolwallet", Decimal("1.5"))
        assert again["psbt"] == built["psbt"]

        txid = "ab" * 32
        attached = ledger.attach_txid(batch_id, txid)
        assert attached["state"] == "broadcast"
        assert attached["txid"] == txid
        assert ledger.get_batch(batch_id)["state"] == "broadcast"

        # Same txid may be re-attached after restart; a different txid is rejected.
        assert ledger.attach_txid(batch_id, txid)["txid"] == txid
        try:
            ledger.attach_txid(batch_id, "cd" * 32)
        except RuntimeError:
            pass
        else:
            raise AssertionError("different txid unexpectedly replaced attached txid")

        checked = paytx.check_payment(ledger, rpc, batch_id, "poolwallet")
        assert checked["state"] == "confirmed", checked
        assert checked["confirmations"] == 6, checked
        assert checked["confirmed_height"] == 106, checked

        paid = ledger.settle(batch_id, 6)
        assert paid["state"] == "paid", paid
        assert ledger.get_batch(batch_id)["state"] == "paid"
        statuses = dict(ledger.db.execute("SELECT status,COUNT(*) FROM credits GROUP BY status").fetchall())
        assert statuses == {"paid": 2}, statuses

        # Settlement is idempotent for already-paid credits.
        paid2 = ledger.settle(batch_id, 6)
        assert paid2["state"] == "paid"
        ledger.close()

    print("CRAK-017 operator-controlled payout lifecycle vectors: OK")


if __name__ == "__main__":
    main()
