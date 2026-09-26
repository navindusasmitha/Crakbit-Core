#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
import time
from pathlib import Path
from typing import Any


def default_manifest_path() -> Path:
    script = Path(__file__).resolve()
    repo_or_prefix = script.parent.parent
    source_path = repo_or_prefix / "network" / "TESTNET_BOOTSTRAP.json"
    if source_path.is_file():
        return source_path
    installed_path = repo_or_prefix / "share" / "crakbit-core" / "network" / "TESTNET_BOOTSTRAP.json"
    return installed_path


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"unable to read bootstrap manifest: {exc}")
    if not isinstance(data, dict):
        raise SystemExit("bootstrap manifest must be a JSON object")
    return data


def parse_endpoint(endpoint: str) -> tuple[str, int]:
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
    host = host.strip()
    if not host:
        raise ValueError("endpoint host is empty")
    try:
        port = int(port_s)
    except ValueError as exc:
        raise ValueError(f"invalid endpoint port: {endpoint}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"endpoint port out of range: {endpoint}")
    return host, port


def obviously_nonpublic_host(host: str) -> bool:
    lowered = host.rstrip(".").lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return True
    if lowered.endswith((".invalid", ".localhost", ".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


def validate(data: dict[str, Any], *, require_public_ready: bool = False) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != 1:
        errors.append("schema must be 1")
    if data.get("network") != "testnet4":
        errors.append("network must be testnet4")

    security = data.get("security")
    if not isinstance(security, dict):
        errors.append("security must be an object")
    else:
        if security.get("rpc_public") is not False:
            errors.append("security.rpc_public must be false")
        if security.get("p2p_public") is not True:
            errors.append("security.p2p_public must be true")
        if security.get("rpc_bind") not in {"127.0.0.1", "::1"}:
            errors.append("security.rpc_bind must be loopback-only")

    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        errors.append("nodes must be a list")
        return errors

    seen_names: set[str] = set()
    seen_endpoints: set[str] = set()
    enabled: list[dict[str, Any]] = []
    for idx, raw in enumerate(nodes):
        prefix = f"nodes[{idx}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = raw.get("name")
        endpoint = raw.get("endpoint")
        region = raw.get("region")
        provider = raw.get("provider")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name is required")
        elif name in seen_names:
            errors.append(f"duplicate node name: {name}")
        else:
            seen_names.add(name)
        if not isinstance(endpoint, str):
            errors.append(f"{prefix}.endpoint is required")
        else:
            try:
                host, _ = parse_endpoint(endpoint)
            except ValueError as exc:
                errors.append(str(exc))
            else:
                normalized = endpoint.lower()
                if normalized in seen_endpoints:
                    errors.append(f"duplicate endpoint: {endpoint}")
                seen_endpoints.add(normalized)
                if require_public_ready and raw.get("enabled") is True and obviously_nonpublic_host(host):
                    errors.append(f"enabled public node is not publicly routable: {endpoint}")
        if not isinstance(region, str) or not region.strip():
            errors.append(f"{prefix}.region is required")
        if not isinstance(provider, str) or not provider.strip():
            errors.append(f"{prefix}.provider is required")
        if raw.get("enabled") not in {True, False}:
            errors.append(f"{prefix}.enabled must be boolean")
        if raw.get("enabled") is True:
            enabled.append(raw)

    if require_public_ready:
        min_nodes = data.get("minimum_public_nodes", 2)
        min_domains = data.get("minimum_failure_domains", 2)
        if not isinstance(min_nodes, int) or min_nodes < 2:
            errors.append("minimum_public_nodes must be an integer >= 2")
        elif len(enabled) < min_nodes:
            errors.append(f"public-ready requires at least {min_nodes} enabled nodes")
        if not isinstance(min_domains, int) or min_domains < 2:
            errors.append("minimum_failure_domains must be an integer >= 2")
        else:
            domains = {(str(n.get("provider", "")).strip().lower(), str(n.get("region", "")).strip().lower()) for n in enabled}
            if len(domains) < min_domains:
                errors.append(f"public-ready requires at least {min_domains} distinct provider/region failure domains")
    return errors


def enabled_nodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in data.get("nodes", []) if isinstance(n, dict) and n.get("enabled") is True]


def render_conf(data: dict[str, Any]) -> str:
    lines = [
        "# CRAK-026 generated testnet4 bootstrap snippet",
        "testnet4=1",
        "server=1",
        "listen=1",
        "rpcbind=127.0.0.1",
        "rpcallowip=127.0.0.1",
    ]
    for node in enabled_nodes(data):
        lines.append(f"addnode={node['endpoint']}")
    return "\n".join(lines) + "\n"


def check_health(data: dict[str, Any], timeout: float) -> tuple[list[dict[str, Any]], int]:
    results: list[dict[str, Any]] = []
    reachable = 0
    for node in enabled_nodes(data):
        endpoint = str(node["endpoint"])
        host, port = parse_endpoint(endpoint)
        started = time.monotonic()
        error: str | None = None
        try:
            with socket.create_connection((host, port), timeout=timeout):
                pass
            ok = True
            reachable += 1
        except OSError as exc:
            ok = False
            error = str(exc)
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        item = {
            "name": node["name"],
            "endpoint": endpoint,
            "region": node["region"],
            "provider": node["provider"],
            "reachable": ok,
            "latency_ms": elapsed_ms,
        }
        if error:
            item["error"] = error
        results.append(item)
    return results, reachable


def main() -> None:
    parser = argparse.ArgumentParser(description="Crakbit public-testnet bootstrap control plane")
    parser.add_argument("--manifest", default=str(default_manifest_path()))
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--require-public-ready", action="store_true")

    p_render = sub.add_parser("render-conf")
    p_render.add_argument("--require-public-ready", action="store_true")

    p_health = sub.add_parser("health")
    p_health.add_argument("--timeout", type=float, default=3.0)
    p_health.add_argument("--minimum-reachable", type=int, default=1)
    p_health.add_argument("--require-public-ready", action="store_true")

    args = parser.parse_args()
    path = Path(args.manifest)
    data = load_manifest(path)
    require_public_ready = bool(getattr(args, "require_public_ready", False))
    errors = validate(data, require_public_ready=require_public_ready)
    if errors:
        for item in errors:
            print(f"ERROR: {item}", file=sys.stderr)
        raise SystemExit(1)

    if args.command == "validate":
        print(f"bootstrap manifest: OK enabled_nodes={len(enabled_nodes(data))} public_ready={require_public_ready}")
        return

    if args.command == "render-conf":
        sys.stdout.write(render_conf(data))
        return

    if args.command == "health":
        if args.timeout <= 0:
            raise SystemExit("--timeout must be > 0")
        if args.minimum_reachable < 0:
            raise SystemExit("--minimum-reachable must be >= 0")
        results, reachable = check_health(data, args.timeout)
        summary = {
            "network": "testnet4",
            "enabled_nodes": len(results),
            "reachable_nodes": reachable,
            "minimum_reachable": args.minimum_reachable,
            "healthy": reachable >= args.minimum_reachable,
            "nodes": results,
        }
        print(json.dumps(summary, sort_keys=True, indent=2))
        if not summary["healthy"]:
            raise SystemExit(1)
        return

    raise SystemExit("unknown command")


if __name__ == "__main__":
    main()
