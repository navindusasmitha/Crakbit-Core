#!/usr/bin/env python3
"""CRAK-019 payout operations monitor and audit helper.

Read/monitor-first operator tooling layered on CRAK-017/018. It does not sign
PSBTs, broadcast transactions, or settle credits automatically. The only
state-changing action is an explicit confirmation refresh using the existing
CRAK-017 verification path.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


def load_guard():
    path = Path(__file__).resolve().parent / "crakpool-payguard.py"
    spec = importlib.util.spec_from_file_location("crakpool_payops_guard", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CRAK-018 crakpool-payguard.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


GUARD = load_guard()
PAYTX = GUARD.PAYTX
BASE = PAYTX.BASE


class OpsLedger(GUARD.GuardLedger):
    def list_records(
        self,
        *,
        state: str | None = None,
        stale_seconds: int = 3600,
        required_confirmations: int = 6,
        preflight_max_age: int = 900,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        if stale_seconds < 1:
            raise ValueError("stale_seconds must be positive")
        if required_confirmations < 1:
            raise ValueError("required_confirmations must be positive")
        if preflight_max_age < 1:
            raise ValueError("preflight_max_age must be positive")
        now = time.time() if now is None else float(now)

        sql = """
            SELECT
                pb.id AS batch_id,
                pb.created_at AS batch_created_at,
                pb.state AS batch_state,
                pb.network,
                pb.total_sats,
                pb.output_count,
                pt.state AS payment_state,
                pt.created_at AS payment_created_at,
                pt.txid,
                pt.attached_at,
                pt.confirmations,
                pt.confirmed_height,
                pt.last_checked_at,
                pt.last_error,
                pt.estimated_fee_sats
            FROM payout_batches AS pb
            LEFT JOIN payout_transactions AS pt ON pt.batch_id=pb.id
        """
        params: list[Any] = []
        if state is not None:
            sql += " WHERE COALESCE(pt.state,pb.state)=?"
            params.append(state)
        sql += " ORDER BY pb.created_at,pb.id"
        rows = self.db.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []

        for row in rows:
            effective_state = str(row["payment_state"] or row["batch_state"])
            latest = self.latest_preflight(str(row["batch_id"]))
            reference_time = self._reference_time(row, effective_state)
            age_seconds = max(0, int(now - reference_time)) if reference_time is not None else None
            stale = age_seconds is not None and age_seconds >= stale_seconds and effective_state not in {"paid", "cancelled"}
            action = self._next_action(
                effective_state=effective_state,
                confirmations=int(row["confirmations"] or 0),
                last_checked_at=float(row["last_checked_at"]) if row["last_checked_at"] is not None else None,
                latest_preflight=latest,
                now=now,
                stale_seconds=stale_seconds,
                required_confirmations=required_confirmations,
                preflight_max_age=preflight_max_age,
            )
            result.append(
                {
                    "batch_id": str(row["batch_id"]),
                    "network": str(row["network"]),
                    "batch_state": str(row["batch_state"]),
                    "payment_state": str(row["payment_state"]) if row["payment_state"] is not None else None,
                    "state": effective_state,
                    "total_sats": int(row["total_sats"]),
                    "output_count": int(row["output_count"]),
                    "txid": str(row["txid"]) if row["txid"] is not None else None,
                    "confirmations": int(row["confirmations"] or 0),
                    "confirmed_height": int(row["confirmed_height"]) if row["confirmed_height"] is not None else None,
                    "estimated_fee_sats": int(row["estimated_fee_sats"]) if row["estimated_fee_sats"] is not None else None,
                    "last_checked_at": float(row["last_checked_at"]) if row["last_checked_at"] is not None else None,
                    "last_error": row["last_error"],
                    "age_seconds": age_seconds,
                    "stale": stale,
                    "next_action": action,
                    "latest_preflight": latest,
                }
            )
        return result

    @staticmethod
    def _reference_time(row: Any, state: str) -> float | None:
        if state in {"broadcast", "confirmed"}:
            for key in ("last_checked_at", "attached_at", "payment_created_at", "batch_created_at"):
                if row[key] is not None:
                    return float(row[key])
            return None
        if state == "psbt_ready":
            if row["payment_created_at"] is not None:
                return float(row["payment_created_at"])
        if row["batch_created_at"] is not None:
            return float(row["batch_created_at"])
        return None

    @staticmethod
    def _next_action(
        *,
        effective_state: str,
        confirmations: int,
        last_checked_at: float | None,
        latest_preflight: dict[str, Any] | None,
        now: float,
        stale_seconds: int,
        required_confirmations: int,
        preflight_max_age: int,
    ) -> str:
        if effective_state == "planned":
            return "build_psbt"
        if effective_state == "psbt_ready":
            if latest_preflight is None:
                return "run_preflight"
            if not bool(latest_preflight["valid"]):
                return "fix_preflight_failure"
            if now - float(latest_preflight["checked_at"]) > preflight_max_age:
                return "run_preflight"
            return "sign_broadcast_then_guarded_attach"
        if effective_state == "broadcast":
            if last_checked_at is None or now - last_checked_at >= stale_seconds:
                return "refresh_confirmations"
            return "wait_confirmations"
        if effective_state == "confirmed":
            if confirmations >= required_confirmations:
                return "settle"
            if last_checked_at is None or now - last_checked_at >= stale_seconds:
                return "refresh_confirmations"
            return "wait_confirmations"
        if effective_state in {"paid", "cancelled"}:
            return "none"
        if effective_state == "invalidated":
            return "manual_review"
        return "manual_review"

    def show_record(
        self,
        batch_id: str,
        *,
        stale_seconds: int = 3600,
        required_confirmations: int = 6,
        preflight_max_age: int = 900,
        now: float | None = None,
    ) -> dict[str, Any]:
        rows = self.list_records(
            stale_seconds=stale_seconds,
            required_confirmations=required_confirmations,
            preflight_max_age=preflight_max_age,
            now=now,
        )
        for row in rows:
            if row["batch_id"] == batch_id:
                return row
        raise RuntimeError(f"unknown payout batch: {batch_id}")

    def summary(
        self,
        *,
        stale_seconds: int = 3600,
        required_confirmations: int = 6,
        preflight_max_age: int = 900,
        now: float | None = None,
    ) -> dict[str, Any]:
        rows = self.list_records(
            stale_seconds=stale_seconds,
            required_confirmations=required_confirmations,
            preflight_max_age=preflight_max_age,
            now=now,
        )
        states = Counter(str(row["state"]) for row in rows)
        actions = Counter(str(row["next_action"]) for row in rows)
        return {
            "batches": len(rows),
            "stale": sum(1 for row in rows if row["stale"]),
            "states": dict(sorted(states.items())),
            "next_actions": dict(sorted(actions.items())),
            "total_sats": sum(int(row["total_sats"]) for row in rows),
        }


def add_monitor_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stale-seconds", type=int, default=3600)
    parser.add_argument("--confirmations", type=int, default=6)
    parser.add_argument("--preflight-max-age", type=int, default=900)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit CRAK-019 payout operations monitor")
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("list", help="list payout batches with operator next-action classification")
    add_monitor_args(ls)
    ls.add_argument("--state")

    show = sub.add_parser("show", help="show one payout batch with CRAK-018 preflight context")
    add_monitor_args(show)
    show.add_argument("--batch", required=True)

    summary = sub.add_parser("summary", help="summarize payout states, stale batches and next actions")
    add_monitor_args(summary)

    refresh = sub.add_parser("refresh", help="explicitly refresh confirmations for one broadcast/confirmed payment")
    PAYTX.add_rpc_args(refresh)
    refresh.add_argument("--batch", required=True)

    args = parser.parse_args()
    ledger = OpsLedger(args.db)
    try:
        if args.command == "list":
            result = ledger.list_records(
                state=args.state,
                stale_seconds=args.stale_seconds,
                required_confirmations=args.confirmations,
                preflight_max_age=args.preflight_max_age,
            )
        elif args.command == "show":
            result = ledger.show_record(
                args.batch,
                stale_seconds=args.stale_seconds,
                required_confirmations=args.confirmations,
                preflight_max_age=args.preflight_max_age,
            )
        elif args.command == "summary":
            result = ledger.summary(
                stale_seconds=args.stale_seconds,
                required_confirmations=args.confirmations,
                preflight_max_age=args.preflight_max_age,
            )
        elif args.command == "refresh":
            payment = ledger.get_payment(args.batch)
            if payment is None or payment["state"] not in {"broadcast", "confirmed", "paid"}:
                raise RuntimeError("refresh requires a broadcast, confirmed, or paid payment")
            if payment["state"] == "paid":
                result = ledger.show_record(args.batch)
            else:
                cli = BASE.resolve_executable(args.cli, "crakbit-cli", "crakbit-cli")
                rpc = BASE.Rpc(cli, args.network, args.datadir, args.rpcport)
                rpc.call("getblockcount")
                PAYTX.check_payment(ledger, rpc, args.batch, args.wallet)
                result = ledger.show_record(args.batch)
        else:
            raise RuntimeError(f"unsupported command: {args.command}")
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        ledger.close()


if __name__ == "__main__":
    raise SystemExit(main())
