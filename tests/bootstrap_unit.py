#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import threading
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "crakbit-bootstrap.py"


def run(args: list[str], *, ok: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(["python3", str(TOOL), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if ok and p.returncode != 0:
        raise AssertionError(p.stdout)
    if not ok and p.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {' '.join(args)}\n{p.stdout}")
    return p


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def listener(port: int, ready: threading.Event, stop: threading.Event) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.listen()
        s.settimeout(0.1)
        ready.set()
        while not stop.is_set():
            try:
                conn, _ = s.accept()
            except TimeoutError:
                continue
            except socket.timeout:
                continue
            with conn:
                pass


def write_manifest(path: Path, nodes: list[dict], **extra: object) -> None:
    data = {
        "schema": 1,
        "network": "testnet4",
        "minimum_public_nodes": 2,
        "minimum_failure_domains": 2,
        "nodes": nodes,
        "security": {"rpc_bind": "127.0.0.1", "rpc_public": False, "p2p_public": True},
    }
    data.update(extra)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        manifest = tmp / "bootstrap.json"

        # The repository template must be valid as a non-live manifest, but not
        # claim public readiness while it still contains disabled .invalid nodes.
        template = ROOT / "network" / "TESTNET_BOOTSTRAP.json"
        good_template = run(["--manifest", str(template), "validate"])
        assert "public_ready=False" in good_template.stdout
        not_ready = run(["--manifest", str(template), "validate", "--require-public-ready"], ok=False)
        assert "public-ready requires at least" in not_ready.stdout

        p1, p2 = free_port(), free_port()
        nodes = [
            {"name": "a", "endpoint": f"127.0.0.1:{p1}", "region": "r1", "provider": "p1", "enabled": True},
            {"name": "b", "endpoint": f"127.0.0.1:{p2}", "region": "r2", "provider": "p2", "enabled": True},
        ]
        write_manifest(manifest, nodes)
        local_ok = run(["--manifest", str(manifest), "validate"])
        assert "enabled_nodes=2" in local_ok.stdout
        local_not_public = run(["--manifest", str(manifest), "validate", "--require-public-ready"], ok=False)
        assert "not publicly routable" in local_not_public.stdout

        rendered = run(["--manifest", str(manifest), "render-conf"]).stdout
        assert "testnet4=1" in rendered
        assert "rpcbind=127.0.0.1" in rendered
        assert f"addnode=127.0.0.1:{p1}" in rendered
        assert f"addnode=127.0.0.1:{p2}" in rendered

        ready1, ready2, stop = threading.Event(), threading.Event(), threading.Event()
        t1 = threading.Thread(target=listener, args=(p1, ready1, stop), daemon=True)
        t2 = threading.Thread(target=listener, args=(p2, ready2, stop), daemon=True)
        t1.start(); t2.start()
        assert ready1.wait(2) and ready2.wait(2)
        try:
            health = run(["--manifest", str(manifest), "health", "--timeout", "1", "--minimum-reachable", "2"])
            payload = json.loads(health.stdout)
            assert payload["healthy"] is True
            assert payload["reachable_nodes"] == 2
        finally:
            stop.set()
            t1.join(1); t2.join(1)

        duplicate = [dict(nodes[0]), dict(nodes[0], name="other")]
        write_manifest(manifest, duplicate)
        dup = run(["--manifest", str(manifest), "validate"], ok=False)
        assert "duplicate endpoint" in dup.stdout

        same_domain = [
            {"name": "a", "endpoint": "seed-a.example.com:48333", "region": "r1", "provider": "p1", "enabled": True},
            {"name": "b", "endpoint": "seed-b.example.com:48333", "region": "r1", "provider": "p1", "enabled": True},
        ]
        write_manifest(manifest, same_domain)
        fail_domain = run(["--manifest", str(manifest), "validate", "--require-public-ready"], ok=False)
        assert "distinct provider/region failure domains" in fail_domain.stdout

        write_manifest(manifest, nodes, security={"rpc_bind": "0.0.0.0", "rpc_public": True, "p2p_public": True})
        unsafe_rpc = run(["--manifest", str(manifest), "validate"], ok=False)
        assert "rpc_public must be false" in unsafe_rpc.stdout
        assert "rpc_bind must be loopback-only" in unsafe_rpc.stdout

    print("CRAK-026 bootstrap unit: OK")


if __name__ == "__main__":
    main()
