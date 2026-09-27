#!/usr/bin/env python3
"""Independent JSON-lines Stratum client used by CRAK-029 interoperability CI."""
from __future__ import annotations

import argparse
import json
import socket
from typing import Any


def send_line(stream, payload: dict[str, Any]) -> None:
    stream.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
    stream.flush()


def recv_line(stream) -> dict[str, Any]:
    line = stream.readline()
    if not line:
        raise RuntimeError("Stratum server closed connection")
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Stratum response is not an object: {payload!r}")
    return payload


def receive_until(stream, predicate, limit: int = 16) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []
    for _ in range(limit):
        message = recv_line(stream)
        seen.append(message)
        if predicate(message):
            return message, seen
    raise RuntimeError(f"expected Stratum response not observed; seen={seen!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="CRAK-029 independent Stratum interoperability probe")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--worker", default="interop.probe")
    parser.add_argument("--password", default="probe")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
        sock.settimeout(args.timeout)
        stream = sock.makefile("rwb", buffering=0)

        send_line(stream, {"id": 1, "method": "mining.subscribe", "params": ["crakbit-independent-probe/1"]})
        subscribe, subscribe_seen = receive_until(stream, lambda m: m.get("id") == 1)
        if subscribe.get("error") is not None:
            raise RuntimeError(f"mining.subscribe failed: {subscribe!r}")
        result = subscribe.get("result")
        if not isinstance(result, list) or len(result) != 3:
            raise RuntimeError(f"unexpected mining.subscribe result: {result!r}")
        subscriptions, extranonce1, extranonce2_size = result
        methods = {item[0] for item in subscriptions if isinstance(item, list) and item}
        if {"mining.set_difficulty", "mining.notify"} - methods:
            raise RuntimeError(f"subscription methods incomplete: {methods!r}")
        if not isinstance(extranonce1, str) or len(extranonce1) != 8:
            raise RuntimeError(f"unexpected extranonce1: {extranonce1!r}")
        if extranonce2_size != 4:
            raise RuntimeError(f"unexpected extranonce2 size: {extranonce2_size!r}")

        difficulty_seen = any(m.get("method") == "mining.set_difficulty" for m in subscribe_seen)
        if not difficulty_seen:
            _, extra = receive_until(stream, lambda m: m.get("method") == "mining.set_difficulty")
            subscribe_seen.extend(extra)

        send_line(stream, {"id": 2, "method": "mining.authorize", "params": [args.worker, args.password]})
        authorize, auth_seen = receive_until(stream, lambda m: m.get("id") == 2)
        if authorize.get("result") is not True or authorize.get("error") is not None:
            raise RuntimeError(f"mining.authorize failed: {authorize!r}")

        notify_seen = any(m.get("method") == "mining.notify" for m in auth_seen)
        if not notify_seen:
            notify, _ = receive_until(stream, lambda m: m.get("method") == "mining.notify")
        else:
            notify = next(m for m in auth_seen if m.get("method") == "mining.notify")
        params = notify.get("params")
        if not isinstance(params, list) or len(params) != 9:
            raise RuntimeError(f"unexpected mining.notify contract: {notify!r}")
        if not isinstance(params[0], str) or not params[0]:
            raise RuntimeError("mining.notify missing job id")

        send_line(stream, {"id": 3, "method": "mining.suggest_difficulty", "params": [0.000000001]})
        suggest, _ = receive_until(stream, lambda m: m.get("id") == 3)
        if suggest.get("result") is not True or suggest.get("error") is not None:
            raise RuntimeError(f"mining.suggest_difficulty compatibility failed: {suggest!r}")

        send_line(stream, {"id": 4, "method": "client.get_version", "params": []})
        unsupported, _ = receive_until(stream, lambda m: m.get("id") == 4)
        error = unsupported.get("error")
        if not isinstance(error, list) or not error or error[0] != 20:
            raise RuntimeError(f"unsupported-method error contract drifted: {unsupported!r}")

    print(
        "CRAK-029 independent Stratum interoperability: OK "
        f"worker={args.worker} subscribe=ok authorize=ok notify=ok suggest=ok"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
