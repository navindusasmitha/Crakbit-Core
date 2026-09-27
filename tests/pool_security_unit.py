#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import ssl
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


edge = load("crakpool_edge_unit", ROOT / "scripts" / "crakpool-edge.py")
worker = load("crakminer_stratum_security_unit", ROOT / "scripts" / "crakminer-stratum.py")


async def rpc(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, payload: dict):
    writer.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=2)
    if not line:
        raise AssertionError("connection closed before response")
    return json.loads(line)


async def gateway_protocol_smoke(policy, auth_path: Path, tls_context=None, client_ssl=None) -> None:
    received: list[dict] = []

    async def upstream_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                message = json.loads(line)
                received.append(message)
                method = message.get("method")
                if method == "mining.subscribe":
                    result = [[["mining.notify", "job"]], "01020304", 4]
                else:
                    result = True
                writer.write(
                    (
                        json.dumps(
                            {"id": message.get("id"), "result": result, "error": None},
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode()
                )
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    upstream = await asyncio.start_server(upstream_handler, "127.0.0.1", 0)
    upstream_port = upstream.sockets[0].getsockname()[1]
    auth = edge.WorkerAuth(auth_path, policy)
    gateway = edge.EdgeGateway(
        policy,
        auth,
        "127.0.0.1",
        0,
        "127.0.0.1",
        upstream_port,
        tls_context,
        None,
    )
    server = await gateway.start()
    port = server.sockets[0].getsockname()[1]

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=client_ssl, server_hostname="localhost" if client_ssl else None)

        subscribe = await rpc(
            reader,
            writer,
            {"id": 1, "method": "mining.subscribe", "params": []},
        )
        assert subscribe["error"] is None
        assert received[-1]["method"] == "mining.subscribe"

        before = len(received)
        bad = await rpc(
            reader,
            writer,
            {"id": 2, "method": "mining.authorize", "params": ["rig1", "wrong"]},
        )
        assert bad["result"] is False
        assert bad["error"][0] == 24
        assert len(received) == before, "bad credential leaked to upstream"

        good = await rpc(
            reader,
            writer,
            {"id": 3, "method": "mining.authorize", "params": ["rig1", "secret-1"]},
        )
        assert good["result"] is True
        assert received[-1]["method"] == "mining.authorize"
        assert received[-1]["params"] == ["rig1", "edge-authenticated"]

        before = len(received)
        mismatch = await rpc(
            reader,
            writer,
            {
                "id": 4,
                "method": "mining.submit",
                "params": ["other", "job", "00000000", "00000000", "00000000"],
            },
        )
        assert mismatch["result"] is False
        assert mismatch["error"][0] == 24
        assert len(received) == before

        accepted = await rpc(
            reader,
            writer,
            {
                "id": 5,
                "method": "mining.submit",
                "params": ["rig1", "job", "00000000", "00000000", "00000000"],
            },
        )
        assert accepted["result"] is True
        assert received[-1]["method"] == "mining.submit"

        before = len(received)
        unsupported = await rpc(
            reader,
            writer,
            {"id": 6, "method": "client.get_version", "params": []},
        )
        assert unsupported["result"] is False
        assert unsupported["error"][0] == 20
        assert len(received) == before

        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()
        upstream.close()
        await upstream.wait_closed()


def main() -> None:
    policy = edge.SecurityPolicy.load(ROOT / "network" / "POOL_SECURITY.json")
    assert policy.public_tls_required is True
    assert policy.worker_auth_required is True
    assert policy.upstream_loopback_required is True
    assert policy.iterations >= 200_000

    assert edge.is_loopback_host("127.0.0.1")
    assert edge.is_loopback_host("::1")
    assert edge.is_loopback_host("localhost")
    assert not edge.is_loopback_host("0.0.0.0")
    assert not edge.is_loopback_host("192.0.2.10")

    assert edge.valid_worker_name("wallet.worker-01", policy)
    assert not edge.valid_worker_name("bad worker", policy)
    assert not edge.valid_worker_name("bad\nworker", policy)
    assert not edge.valid_worker_name("", policy)

    bucket = edge.TokenBucket(1.0, 2.0)
    bucket.updated = 100.0
    bucket.tokens = 2.0
    assert bucket.consume(now=100.0)
    assert bucket.consume(now=100.0)
    assert not bucket.consume(now=100.0)
    assert bucket.consume(now=101.0)

    guard = edge.AbuseGuard(policy)
    now = 1000.0
    for _ in range(policy.max_failures_per_window - 1):
        assert guard.record_auth_failure("198.51.100.10", now=now) is False
    assert guard.record_auth_failure("198.51.100.10", now=now) is True
    assert guard.is_banned("198.51.100.10", now=now + 1)
    assert not guard.is_banned("198.51.100.10", now=now + policy.ban_seconds + 1)

    with tempfile.TemporaryDirectory(prefix="crak028-") as td:
        root = Path(td)
        auth_path = root / "workers.json"
        edge.write_worker_credential(auth_path, "rig1", "secret-1", policy)
        if os.name == "posix":
            assert (auth_path.stat().st_mode & 0o077) == 0
        auth = edge.WorkerAuth(auth_path, policy)
        assert auth.verify("rig1", "secret-1")
        assert not auth.verify("rig1", "wrong")
        assert not auth.verify("unknown", "secret-1")

        miner_secret = root / "miner.secret"
        miner_secret.write_text("secret-1\n", encoding="utf-8")
        if os.name == "posix":
            os.chmod(miner_secret, 0o600)
        assert worker.load_worker_secret(None, str(miner_secret), False) == "secret-1"
        assert worker.load_worker_secret("legacy-x", None, False) == "legacy-x"

        try:
            edge.validate_serve_config("0.0.0.0", "127.0.0.1", None, auth, policy)
        except ValueError as exc:
            assert "requires TLS" in str(exc)
        else:
            raise AssertionError("public plaintext bind was accepted")

        try:
            edge.validate_serve_config("127.0.0.1", "203.0.113.10", None, auth, policy)
        except ValueError as exc:
            assert "loopback" in str(exc)
        else:
            raise AssertionError("non-loopback upstream was accepted")

        asyncio.run(gateway_protocol_smoke(policy, auth_path))

        if shutil.which("openssl"):
            key_path = root / "edge.key"
            cert_path = root / "edge.crt"
            subprocess.run(
                [
                    "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key_path), "-out", str(cert_path),
                    "-days", "1", "-subj", "/CN=localhost",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if os.name == "posix":
                os.chmod(key_path, 0o600)
            server_tls = edge.build_tls_context(cert_path, key_path)
            assert server_tls is not None
            assert server_tls.minimum_version >= ssl.TLSVersion.TLSv1_2
            edge.validate_serve_config("0.0.0.0", "127.0.0.1", server_tls, auth, policy)

            verified_client = worker.make_tls_context(str(cert_path))
            assert verified_client.minimum_version >= ssl.TLSVersion.TLSv1_2
            assert verified_client.verify_mode == ssl.CERT_REQUIRED
            assert verified_client.check_hostname is True

            client_tls = ssl.create_default_context()
            client_tls.check_hostname = False
            client_tls.verify_mode = ssl.CERT_NONE
            asyncio.run(gateway_protocol_smoke(policy, auth_path, server_tls, client_tls))

    print("CRAK-028 pool security unit/gateway smoke: OK")


if __name__ == "__main__":
    main()
