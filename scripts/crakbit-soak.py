#!/usr/bin/env python3
"""CRAK-027 public-testnet soak evidence collector and evaluator.

The collector talks only to a node's local crakbit-cli/RPC path. It never opens,
proxies, or probes public RPC. The evaluator consumes append-only JSONL evidence
from independently operated nodes and applies the reviewed soak policy.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"unable to read JSON {path}: {exc}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON root must be an object: {path}")
    return value


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid JSONL {path}:{line_no}: {exc}")
        if not isinstance(value, dict):
            raise SystemExit(f"JSONL record must be an object: {path}:{line_no}")
        records.append(value)
    return records


def now_record_time() -> tuple[int, str]:
    epoch = int(time.time())
    iso = datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")
    return epoch, iso


def rpc_json(cli: str, datadir: str | None, method: str) -> Any:
    cmd = [cli, "-testnet4"]
    if datadir:
        cmd.append(f"-datadir={datadir}")
    cmd.append(method)
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=20, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"{method} failed rc={proc.returncode}: {detail[:500]}")
    text = proc.stdout.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{method} returned non-JSON output: {text[:200]}") from exc


def collect_observation(node: str, cli: str, datadir: str | None) -> dict[str, Any]:
    epoch, iso = now_record_time()
    base: dict[str, Any] = {
        "schema": 1,
        "kind": "observation",
        "network": "testnet4",
        "node": node,
        "timestamp_epoch": epoch,
        "timestamp_utc": iso,
    }
    try:
        chain = rpc_json(cli, datadir, "getblockchaininfo")
        net = rpc_json(cli, datadir, "getnetworkinfo")
        uptime = rpc_json(cli, datadir, "uptime")
        if not isinstance(chain, dict) or not isinstance(net, dict):
            raise RuntimeError("unexpected RPC result shape")
        base.update(
            {
                "healthy": True,
                "blocks": int(chain["blocks"]),
                "headers": int(chain["headers"]),
                "bestblockhash": str(chain["bestblockhash"]),
                "initialblockdownload": bool(chain.get("initialblockdownload", False)),
                "verificationprogress": float(chain.get("verificationprogress", 0.0)),
                "connections": int(net.get("connections", 0)),
                "connections_in": int(net.get("connections_in", 0)),
                "connections_out": int(net.get("connections_out", 0)),
                "uptime_seconds": int(uptime),
            }
        )
    except Exception as exc:
        base.update({"healthy": False, "error": str(exc)[:800]})
    return base


def parse_host(endpoint: str) -> str:
    endpoint = endpoint.strip()
    if endpoint.startswith("["):
        end = endpoint.find("]")
        if end <= 1 or end + 1 >= len(endpoint) or endpoint[end + 1] != ":":
            raise ValueError(f"invalid endpoint: {endpoint}")
        host = endpoint[1:end]
        port_s = endpoint[end + 2 :]
    else:
        if endpoint.count(":") != 1:
            raise ValueError(f"endpoint must be host:port or [ipv6]:port: {endpoint}")
        host, port_s = endpoint.rsplit(":", 1)
    if not host:
        raise ValueError("endpoint host is empty")
    port = int(port_s)
    if not 1 <= port <= 65535:
        raise ValueError(f"endpoint port out of range: {endpoint}")
    return host


def nonpublic_host(host: str) -> bool:
    value = host.rstrip(".").lower()
    if value in {"localhost", "localhost.localdomain"}:
        return True
    if value.endswith((".invalid", ".localhost", ".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema") != 1:
        errors.append("policy schema must be 1")
    if policy.get("network") != "testnet4":
        errors.append("policy network must be testnet4")
    integer_keys = [
        "minimum_nodes",
        "minimum_failure_domains",
        "maximum_consecutive_failures",
        "maximum_tip_height_spread",
        "maximum_header_lag",
        "minimum_peer_connections",
        "maximum_reorg_depth",
    ]
    for key in integer_keys:
        if not isinstance(policy.get(key), int) or int(policy[key]) < 0:
            errors.append(f"policy {key} must be a non-negative integer")
    for key in ("minimum_availability_ratio", "minimum_verification_progress"):
        value = policy.get(key)
        if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            errors.append(f"policy {key} must be between 0 and 1")
    qualification = policy.get("qualification")
    if not isinstance(qualification, dict):
        errors.append("policy qualification must be an object")
    else:
        for name in ("smoke", "candidate", "launch"):
            item = qualification.get(name)
            if not isinstance(item, dict):
                errors.append(f"policy qualification.{name} is required")
                continue
            if not isinstance(item.get("minimum_window_seconds"), int) or item["minimum_window_seconds"] < 0:
                errors.append(f"qualification.{name}.minimum_window_seconds must be >= 0")
            for flag in ("require_restart_recovery", "require_reorg_observation"):
                if item.get(flag) not in {True, False}:
                    errors.append(f"qualification.{name}.{flag} must be boolean")
    return errors


def enabled_bootstrap_nodes(bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = bootstrap.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    return [item for item in nodes if isinstance(item, dict) and item.get("enabled") is True]


def validate_public_bootstrap(bootstrap: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if bootstrap.get("network") != "testnet4":
        errors.append("bootstrap network must be testnet4")
    nodes = enabled_bootstrap_nodes(bootstrap)
    minimum_nodes = max(int(policy["minimum_nodes"]), int(bootstrap.get("minimum_public_nodes", 0)))
    if len(nodes) < minimum_nodes:
        errors.append(f"need at least {minimum_nodes} enabled public nodes, found {len(nodes)}")
    names: set[str] = set()
    domains: set[tuple[str, str]] = set()
    for node in nodes:
        name = str(node.get("name", "")).strip()
        endpoint = str(node.get("endpoint", "")).strip()
        provider = str(node.get("provider", "")).strip().lower()
        region = str(node.get("region", "")).strip().lower()
        if not name:
            errors.append("enabled bootstrap node is missing a name")
        elif name in names:
            errors.append(f"duplicate enabled node name: {name}")
        names.add(name)
        if provider and region:
            domains.add((provider, region))
        try:
            host = parse_host(endpoint)
        except Exception as exc:
            errors.append(str(exc))
        else:
            if nonpublic_host(host):
                errors.append(f"enabled node is not publicly routable: {endpoint}")
    minimum_domains = max(int(policy["minimum_failure_domains"]), int(bootstrap.get("minimum_failure_domains", 0)))
    if len(domains) < minimum_domains:
        errors.append(f"need at least {minimum_domains} provider/region failure domains, found {len(domains)}")
    security = bootstrap.get("security", {})
    if not isinstance(security, dict) or security.get("rpc_public") is not False:
        errors.append("bootstrap RPC must remain non-public")
    if isinstance(security, dict) and security.get("rpc_bind") not in {"127.0.0.1", "::1"}:
        errors.append("bootstrap RPC bind must remain loopback-only")
    return errors


def longest_failure_run(records: list[dict[str, Any]]) -> int:
    longest = current = 0
    for record in records:
        if record.get("healthy") is True:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return longest


def healthy_after(records: list[dict[str, Any]], timestamp: int) -> bool:
    return any(int(r.get("timestamp_epoch", -1)) > timestamp and r.get("healthy") is True for r in records)


def evaluate(
    bootstrap: dict[str, Any],
    policy: dict[str, Any],
    observations: list[dict[str, Any]],
    events: list[dict[str, Any]],
    qualification_name: str,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    if errors:
        return {"healthy": False, "qualification": qualification_name, "errors": errors}
    qualifications = policy["qualification"]
    if qualification_name not in qualifications:
        return {"healthy": False, "qualification": qualification_name, "errors": ["unknown qualification"]}
    q = qualifications[qualification_name]
    errors.extend(validate_public_bootstrap(bootstrap, policy))

    enabled = enabled_bootstrap_nodes(bootstrap)
    enabled_names = [str(n.get("name", "")) for n in enabled if str(n.get("name", ""))]
    histories: dict[str, list[dict[str, Any]]] = {name: [] for name in enabled_names}
    for record in observations:
        if record.get("kind") != "observation" or record.get("network") != "testnet4":
            continue
        node = str(record.get("node", ""))
        if node in histories and isinstance(record.get("timestamp_epoch"), int):
            histories[node].append(record)
    for records in histories.values():
        records.sort(key=lambda item: int(item["timestamp_epoch"]))

    node_summaries: dict[str, Any] = {}
    latest_healthy: dict[str, dict[str, Any]] = {}
    earliest_height: list[int] = []
    latest_height: list[int] = []
    restart_recovered = 0
    minimum_window = int(q["minimum_window_seconds"])

    for name in enabled_names:
        records = histories.get(name, [])
        if not records:
            errors.append(f"no soak observations for enabled node {name}")
            continue
        healthy_records = [r for r in records if r.get("healthy") is True]
        availability = len(healthy_records) / len(records)
        failure_run = longest_failure_run(records)
        window = int(records[-1]["timestamp_epoch"]) - int(records[0]["timestamp_epoch"])
        if availability < float(policy["minimum_availability_ratio"]):
            errors.append(f"{name} availability {availability:.5f} below {policy['minimum_availability_ratio']}")
        if failure_run > int(policy["maximum_consecutive_failures"]):
            errors.append(f"{name} consecutive failures {failure_run} exceed {policy['maximum_consecutive_failures']}")
        if window < minimum_window:
            errors.append(f"{name} observation window {window}s below required {minimum_window}s")
        if not healthy_records:
            errors.append(f"{name} has no healthy observation")
            continue
        first = healthy_records[0]
        latest = healthy_records[-1]
        latest_healthy[name] = latest
        first_blocks = int(first.get("blocks", -1))
        last_blocks = int(latest.get("blocks", -1))
        earliest_height.append(first_blocks)
        latest_height.append(last_blocks)
        if bool(latest.get("initialblockdownload", True)):
            errors.append(f"{name} is still in initial block download")
        if float(latest.get("verificationprogress", 0.0)) < float(policy["minimum_verification_progress"]):
            errors.append(f"{name} verification progress below threshold")
        if int(latest.get("connections", 0)) < int(policy["minimum_peer_connections"]):
            errors.append(f"{name} peer connections below threshold")
        if int(latest.get("headers", -1)) - last_blocks > int(policy["maximum_header_lag"]):
            errors.append(f"{name} header lag exceeds threshold")

        node_events = [e for e in events if e.get("node") == name and e.get("network") == "testnet4"]
        recovered_for_node = False
        for event in node_events:
            if event.get("event") == "restart" and isinstance(event.get("timestamp_epoch"), int):
                if healthy_after(records, int(event["timestamp_epoch"])):
                    recovered_for_node = True
                    break
        if recovered_for_node:
            restart_recovered += 1
        elif q.get("require_restart_recovery") is True:
            errors.append(f"{name} has no proven restart recovery")

        node_summaries[name] = {
            "samples": len(records),
            "healthy_samples": len(healthy_records),
            "availability_ratio": round(availability, 6),
            "maximum_consecutive_failures": failure_run,
            "window_seconds": window,
            "first_height": first_blocks,
            "latest_height": last_blocks,
            "latest_hash": str(latest.get("bestblockhash", "")),
            "latest_connections": int(latest.get("connections", 0)),
            "restart_recovered": recovered_for_node,
        }

    height_spread: int | None = None
    if latest_healthy:
        heights = [int(r.get("blocks", -1)) for r in latest_healthy.values()]
        height_spread = max(heights) - min(heights)
        if height_spread > int(policy["maximum_tip_height_spread"]):
            errors.append(f"final tip height spread {height_spread} exceeds {policy['maximum_tip_height_spread']}")
        if len(set(heights)) == 1:
            hashes = {str(r.get("bestblockhash", "")) for r in latest_healthy.values()}
            if len(hashes) != 1:
                errors.append("nodes report conflicting block hashes at the same final height")

    progress_blocks = 0
    if earliest_height and latest_height:
        progress_blocks = max(latest_height) - min(earliest_height)
        if progress_blocks <= 0:
            errors.append("no chain/mining progress observed during soak window")

    valid_reorgs: list[dict[str, Any]] = []
    for event in events:
        if event.get("event") != "reorg" or event.get("network") != "testnet4":
            continue
        node = str(event.get("node", ""))
        depth = event.get("depth")
        timestamp = event.get("timestamp_epoch")
        if node not in histories or not isinstance(depth, int) or depth <= 0 or not isinstance(timestamp, int):
            continue
        if depth > int(policy["maximum_reorg_depth"]):
            errors.append(f"recorded reorg depth {depth} exceeds policy maximum {policy['maximum_reorg_depth']}")
            continue
        if healthy_after(histories[node], timestamp):
            valid_reorgs.append(event)
    if q.get("require_reorg_observation") is True and not valid_reorgs:
        errors.append("launch qualification requires a recovered reorg observation")

    return {
        "schema": 1,
        "network": "testnet4",
        "qualification": qualification_name,
        "healthy": not errors,
        "errors": errors,
        "enabled_nodes": len(enabled_names),
        "restart_recoveries": restart_recovered,
        "reorg_observations": len(valid_reorgs),
        "final_tip_height_spread": height_spread,
        "progress_blocks": progress_blocks,
        "nodes": node_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Crakbit public-testnet soak evidence tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="append one local-RPC node observation")
    p_collect.add_argument("--node", required=True)
    p_collect.add_argument("--output", required=True)
    p_collect.add_argument("--cli", default="crakbit-cli")
    p_collect.add_argument("--datadir")

    p_event = sub.add_parser("event", help="append a restart or reorg evidence event")
    p_event.add_argument("--node", required=True)
    p_event.add_argument("--event", choices=("restart", "reorg"), required=True)
    p_event.add_argument("--output", required=True)
    p_event.add_argument("--depth", type=int)
    p_event.add_argument("--note", default="")

    p_eval = sub.add_parser("evaluate", help="evaluate multi-node soak evidence")
    p_eval.add_argument("--bootstrap", default="network/TESTNET_BOOTSTRAP.json")
    p_eval.add_argument("--policy", default="network/SOAK_POLICY.json")
    p_eval.add_argument("--observations-dir", required=True)
    p_eval.add_argument("--events", required=True)
    p_eval.add_argument("--qualification", choices=("smoke", "candidate", "launch"), default="smoke")
    p_eval.add_argument("--output")

    args = parser.parse_args()

    if args.command == "collect":
        record = collect_observation(args.node, args.cli, args.datadir)
        append_jsonl(Path(args.output), record)
        print(json.dumps(record, sort_keys=True, indent=2))
        if record.get("healthy") is not True:
            raise SystemExit(1)
        return

    if args.command == "event":
        if args.event == "reorg" and (args.depth is None or args.depth <= 0):
            raise SystemExit("reorg events require --depth > 0")
        if args.event == "restart" and args.depth is not None:
            raise SystemExit("restart events do not accept --depth")
        epoch, iso = now_record_time()
        record: dict[str, Any] = {
            "schema": 1,
            "kind": "event",
            "network": "testnet4",
            "node": args.node,
            "event": args.event,
            "timestamp_epoch": epoch,
            "timestamp_utc": iso,
            "note": args.note,
        }
        if args.depth is not None:
            record["depth"] = args.depth
        append_jsonl(Path(args.output), record)
        print(json.dumps(record, sort_keys=True, indent=2))
        return

    if args.command == "evaluate":
        bootstrap = load_json(Path(args.bootstrap))
        policy = load_json(Path(args.policy))
        observation_dir = Path(args.observations_dir)
        if not observation_dir.is_dir():
            raise SystemExit(f"observations directory not found: {observation_dir}")
        observations: list[dict[str, Any]] = []
        for path in sorted(observation_dir.glob("*.jsonl")):
            observations.extend(load_jsonl(path))
        events = load_jsonl(Path(args.events))
        result = evaluate(bootstrap, policy, observations, events, args.qualification)
        rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(rendered, encoding="utf-8")
        sys.stdout.write(rendered)
        if result.get("healthy") is not True:
            raise SystemExit(1)
        return

    raise SystemExit("unknown command")


if __name__ == "__main__":
    main()
