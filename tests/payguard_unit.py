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


accounting = load("crakpool_accounting_payguard_test", ROOT / "scripts" / "crakpool-accounting.py")
payout = load("crakpool_payout_payguard_test", ROOT / "scripts" / "crakpool-payout.py")
paytx = load("crakpool_paytx_payguard_test", ROOT / "scripts" / "crakpool-paytx.py")
payguard = load("crakpool_payguard_unit", ROOT / "scripts" / "crakpool-payguard.py")


class FakeRpc:
    def __init__(self, *, reorg: bool = False, wrong_output: bool = False):
        self.reorg = reorg
        self.wrong_output = wrong_output
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
                return ("03" if self.reorg else "02") * 32
            return f"{height:064x}"[-64:]
        if method == "decodepsbt":
            assert params[0] == "cHNidP8BAFake"
            alice = 0.00000049 if self.wrong_output else 0.00000050
            return {
                "tx": {
                    "vin": [
                        {"txid": "11" * 32, "vout": 0},
                        {"txid": "22" * 32, "vout": 3},
                    ],
                    "vout": [
                        {"value": alice, "scriptPubKey": {"address": "crak1alice"}},
                        {"value": 0.00000050, "scriptPubKey": {"address": "crak1bob"}},
                        {"value": 1.0, "scriptPubKey": {"address": "rcrak1change"}},
                    ],
                }
            }
        if method == "lockunspent":
            assert wallet == "poolwallet"
            assert params[0] == "true"
            assert '"txid":"1111111111111111111111111111111111111111111111111111111111111111"' in params[1]
            assert '"txid":"2222222222222222222222222222222222222222222222222222222222222222"' in params[1]
            return True
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

    txledger = paytx.PaymentLedger(db)
    payment = txledger.persist_psbt(batch_id, "cHNidP8BAFake", 123)
    assert payment["state"] == "psbt_ready"
    txledger.close()
    return batch_id


def expect_runtime(fn, text: str) -> None:
    try:
        fn()
    except RuntimeError as exc:
        assert text in str(exc), exc
    else:
        raise AssertionError(f"expected RuntimeError containing {text!r}")


def main() -> None:
    # Happy path: current canonical mature sources + exact outputs create an audit
    # preflight, then a fresh preflight permits guarded txid attachment.
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch_id = seed_db(db)
        rpc = FakeRpc()
        ledger = payguard.GuardLedger(db)
        result = payguard.preflight(ledger, rpc, batch_id, max_fee_sats=200)
        assert result["safe_to_sign_and_broadcast_externally"] is True
        assert result["input_count"] == 2
        assert result["preflight"]["valid"] is True
        assert result["estimated_fee_sats"] == 123

        attached = payguard.guarded_attach(
            ledger,
            batch_id,
            "ab" * 32,
            max_age_seconds=900,
        )
        assert attached["state"] == "broadcast"
        assert attached["txid"] == "ab" * 32
        ledger.close()

    # Cancellation requires explicit operator attestation, unlocks exactly the
    # PSBT inputs, preserves the audit row, and releases canonical credits.
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch_id = seed_db(db)
        rpc = FakeRpc()
        ledger = payguard.GuardLedger(db)
        payguard.preflight(ledger, rpc, batch_id)
        expect_runtime(
            lambda: payguard.cancel(
                ledger,
                rpc,
                batch_id,
                "poolwallet",
                confirm_not_broadcast=False,
            ),
            "--confirm-not-broadcast",
        )
        cancelled = payguard.cancel(
            ledger,
            rpc,
            batch_id,
            "poolwallet",
            confirm_not_broadcast=True,
        )
        assert cancelled["state"] == "cancelled"
        assert ledger.get_batch(batch_id)["state"] == "cancelled"
        statuses = dict(ledger.db.execute("SELECT status,COUNT(*) FROM credits GROUP BY status").fetchall())
        assert statuses == {"pending": 2}, statuses
        assert ledger.latest_preflight(batch_id)["valid"] is True
        ledger.close()

    # A source-block reorg after PSBT creation must fail closed and leave an
    # auditable failed preflight. No txid can be guarded-attached afterward.
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch_id = seed_db(db)
        rpc = FakeRpc(reorg=True)
        ledger = payguard.GuardLedger(db)
        expect_runtime(
            lambda: payguard.preflight(ledger, rpc, batch_id),
            "source block is not canonical",
        )
        latest = ledger.latest_preflight(batch_id)
        assert latest is not None and latest["valid"] is False
        expect_runtime(
            lambda: payguard.guarded_attach(
                ledger,
                batch_id,
                "cd" * 32,
                max_age_seconds=900,
            ),
            "no successful CRAK-018 preflight",
        )
        ledger.close()

    # Recipient tampering in the funded PSBT is rejected before signing.
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch_id = seed_db(db)
        rpc = FakeRpc(wrong_output=True)
        ledger = payguard.GuardLedger(db)
        expect_runtime(
            lambda: payguard.preflight(ledger, rpc, batch_id),
            "does not match payout batch output",
        )
        assert ledger.latest_preflight(batch_id)["valid"] is False
        ledger.close()

    # Max-fee policy is an optional operator hard cap.
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "pool.sqlite3"
        batch_id = seed_db(db)
        rpc = FakeRpc()
        ledger = payguard.GuardLedger(db)
        expect_runtime(
            lambda: payguard.preflight(ledger, rpc, batch_id, max_fee_sats=100),
            "exceeds max 100 sats",
        )
        assert ledger.latest_preflight(batch_id)["valid"] is False
        ledger.close()

    print("CRAK-018 payout preflight/recovery vectors: OK")


if __name__ == "__main__":
    main()
