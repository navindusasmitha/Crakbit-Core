#!/usr/bin/env python3
"""CRAK-013 native Crakbit yespower miner controller.

The node supplies getblocktemplate data and validates submitblock. CPU hashing is
performed by the standalone crakminer-scan binary against the canonical 80-byte
header; the node's generate* RPC methods are not used by this miner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path


def hash256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative varint")
    if value < 0xFD:
        return bytes([value])
    if value <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", value)
    if value <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", value)
    return b"\xff" + struct.pack("<Q", value)


def scriptnum(value: int) -> bytes:
    if value == 0:
        return b""
    if value < 0:
        raise ValueError("negative script number unsupported")
    out = bytearray()
    while value:
        out.append(value & 0xFF)
        value >>= 8
    if out[-1] & 0x80:
        out.append(0)
    return bytes(out)


def push_data(data: bytes) -> bytes:
    size = len(data)
    if size < 0x4C:
        return bytes([size]) + data
    if size <= 0xFF:
        return b"\x4c" + bytes([size]) + data
    if size <= 0xFFFF:
        return b"\x4d" + struct.pack("<H", size) + data
    raise ValueError("push_data too large")


def bip34_height_prefix(height: int) -> bytes:
    """Match Bitcoin Core's `CScript() << nHeight` byte-for-byte."""
    if height < 0:
        raise ValueError("negative block height")
    if height == 0:
        return b"\x00"  # OP_0
    if 1 <= height <= 16:
        return bytes([0x50 + height])  # OP_1 .. OP_16
    return push_data(scriptnum(height))


def merkle_root_internal(leaves: list[bytes]) -> bytes:
    if not leaves:
        raise ValueError("empty merkle tree")
    level = leaves[:]
    while len(level) > 1:
        if len(level) & 1:
            level.append(level[-1])
        level = [hash256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def compact_target(bits_hex: str) -> str:
    compact = int(bits_hex, 16)
    exponent = compact >> 24
    mantissa = compact & 0x007FFFFF
    if compact & 0x00800000:
        raise ValueError("negative compact target")
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    if target <= 0 or target >= 1 << 256:
        raise ValueError("compact target outside uint256 range")
    return f"{target:064x}"


def build_coinbase(template: dict, payout_script: bytes, extranonce: int) -> tuple[bytes, bytes]:
    height = int(template["height"])
    flags_hex = template.get("coinbaseaux", {}).get("flags", "")
    flags = bytes.fromhex(flags_hex) if flags_hex else b""
    extra = struct.pack("<Q", extranonce & 0xFFFFFFFFFFFFFFFF)
    script_sig = bip34_height_prefix(height) + flags + push_data(extra)
    if not 2 <= len(script_sig) <= 100:
        raise ValueError(f"coinbase scriptSig length {len(script_sig)} outside 2..100")

    version = struct.pack("<I", 2)
    vin = (
        varint(1)
        + (b"\x00" * 32)
        + struct.pack("<I", 0xFFFFFFFF)
        + varint(len(script_sig))
        + script_sig
        + struct.pack("<I", 0xFFFFFFFF)
    )

    outputs: list[bytes] = []
    reward = int(template["coinbasevalue"])
    outputs.append(struct.pack("<Q", reward) + varint(len(payout_script)) + payout_script)

    commitment_hex = template.get("default_witness_commitment")
    commitment = bytes.fromhex(commitment_hex) if commitment_hex else b""
    if commitment:
        outputs.append(struct.pack("<Q", 0) + varint(len(commitment)) + commitment)

    vout = varint(len(outputs)) + b"".join(outputs)
    locktime = struct.pack("<I", 0)
    stripped = version + vin + vout + locktime

    if commitment:
        # BIP141 coinbase witness reserved value. The node-provided default
        # commitment is computed for the template transactions and 32 zero bytes.
        witness = varint(1) + varint(32) + (b"\x00" * 32)
        full = version + b"\x00\x01" + vin + vout + witness + locktime
    else:
        full = stripped

    return full, hash256(stripped)


def build_candidate(template: dict, payout_script: bytes, extranonce: int) -> tuple[bytearray, bytes, str]:
    coinbase, coinbase_txid_internal = build_coinbase(template, payout_script, extranonce)

    txids = [coinbase_txid_internal]
    tx_data = []
    for tx in template.get("transactions", []):
        txids.append(bytes.fromhex(tx["txid"])[::-1])
        tx_data.append(bytes.fromhex(tx["data"]))

    merkle = merkle_root_internal(txids)
    version = int(template["version"])
    if not -(1 << 31) <= version < (1 << 31):
        raise ValueError("template version outside int32 range")
    previous = bytes.fromhex(template["previousblockhash"])[::-1]
    curtime = int(template["curtime"])
    bits_hex = template["bits"]
    bits = int(bits_hex, 16)

    header = bytearray(
        struct.pack("<i", version)
        + previous
        + merkle
        + struct.pack("<I", curtime)
        + struct.pack("<I", bits)
        + struct.pack("<I", 0)
    )
    if len(header) != 80:
        raise AssertionError(f"header length is {len(header)}, expected 80")

    block_tail = varint(1 + len(tx_data)) + coinbase + b"".join(tx_data)
    target = template.get("target") or compact_target(bits_hex)
    if len(target) != 64:
        raise ValueError("template target is not 256-bit hex")
    return header, block_tail, target.lower()


class Rpc:
    def __init__(self, cli: str, network: str, datadir: str, rpcport: int | None):
        self.base = [cli, "-testnet4" if network == "testnet4" else "-regtest", f"-datadir={datadir}"]
        if rpcport is not None:
            self.base.append(f"-rpcport={rpcport}")

    def call(self, method: str, *params: str, wallet: str | None = None, parse_json: bool = True):
        cmd = self.base[:]
        if wallet:
            cmd.append(f"-rpcwallet={wallet}")
        cmd.extend([method, *params])
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise RuntimeError(f"RPC {method} failed: {proc.stderr.strip() or proc.stdout.strip()}")
        text = proc.stdout.strip()
        if not parse_json:
            return text
        if text == "":
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


def resolve_executable(explicit: str | None, sibling: str, path_name: str) -> str:
    if explicit:
        return explicit
    here = Path(__file__).resolve().parent
    sibling_path = here / sibling
    if sibling_path.exists() and os.access(sibling_path, os.X_OK):
        return str(sibling_path)
    found = shutil.which(path_name)
    if found:
        return found
    raise SystemExit(f"{path_name} not found; use the explicit path option")


def parse_scan_result(text: str) -> tuple[int, str, int]:
    fields: dict[str, str] = {}
    for token in text.strip().split():
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value
    if not {"nonce", "hash", "attempts"} <= fields.keys():
        raise ValueError(f"unexpected scanner output: {text!r}")
    return int(fields["nonce"]), fields["hash"].lower(), int(fields["attempts"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Crakbit native yespower getblocktemplate miner")
    parser.add_argument("--network", choices=["testnet4", "regtest"], default="testnet4")
    dest = parser.add_mutually_exclusive_group(required=True)
    dest.add_argument("--wallet")
    dest.add_argument("--address")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--cpu-limit", type=int, default=100)
    parser.add_argument("--blocks", type=int, default=0, help="0 mines continuously")
    parser.add_argument("--batch-hashes", type=int, default=250000)
    parser.add_argument("--datadir", default=os.environ.get("CRAKBIT_DATADIR", str(Path.home() / ".crakbit")))
    parser.add_argument("--rpcport", type=int)
    parser.add_argument("--cli")
    parser.add_argument("--scanner")
    args = parser.parse_args()

    if not 1 <= args.threads <= 256:
        parser.error("--threads must be between 1 and 256")
    if not 1 <= args.cpu_limit <= 100:
        parser.error("--cpu-limit must be between 1 and 100")
    if args.blocks < 0:
        parser.error("--blocks cannot be negative")
    if args.batch_hashes < 1:
        parser.error("--batch-hashes must be greater than zero")

    cli = resolve_executable(args.cli, "crakbit-cli", "crakbit-cli")
    scanner = resolve_executable(args.scanner, "crakminer-scan", "crakminer-scan")
    rpc = Rpc(cli, args.network, args.datadir, args.rpcport)
    rpc.call("getblockcount")

    if args.wallet:
        address = rpc.call("getnewaddress", "", "bech32", wallet=args.wallet, parse_json=False)
    else:
        address = args.address
    assert address is not None

    addr = rpc.call("validateaddress", address)
    if not isinstance(addr, dict) or not addr.get("isvalid"):
        raise SystemExit(f"invalid mining address for {args.network}: {address}")
    script_hex = addr.get("scriptPubKey")
    if not script_hex and args.wallet:
        info = rpc.call("getaddressinfo", address, wallet=args.wallet)
        script_hex = info.get("scriptPubKey") if isinstance(info, dict) else None
    if not script_hex:
        raise SystemExit("node did not return payout scriptPubKey")
    payout_script = bytes.fromhex(script_hex)

    accepted = 0
    extranonce = int(time.time_ns()) & 0xFFFFFFFFFFFFFFFF
    print(
        f"crakminer-native network={args.network} threads={args.threads} "
        f"cpu_limit={args.cpu_limit}% blocks={args.blocks} batch_hashes={args.batch_hashes} address={address}",
        flush=True,
    )

    try:
        while args.blocks == 0 or accepted < args.blocks:
            template = rpc.call("getblocktemplate", json.dumps({"rules": ["segwit"]}, separators=(",", ":")))
            if not isinstance(template, dict):
                raise RuntimeError("getblocktemplate did not return an object")

            extranonce = (extranonce + 1) & 0xFFFFFFFFFFFFFFFF
            header, block_tail, target = build_candidate(template, payout_script, extranonce)
            scan_cmd = [
                scanner,
                "--header",
                header.hex(),
                "--target",
                target,
                "--threads",
                str(args.threads),
                "--cpu-limit",
                str(args.cpu_limit),
                "--max-hashes",
                str(args.batch_hashes),
            ]
            started = time.monotonic()
            scan = subprocess.run(scan_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            elapsed = max(time.monotonic() - started, 1e-9)

            if scan.returncode == 2:
                attempts = 0
                for token in scan.stdout.split():
                    if token.startswith("attempts="):
                        attempts = int(token.split("=", 1)[1])
                rate = attempts / elapsed if attempts else 0.0
                print(f"crakminer-native refresh no-solution attempts={attempts} rate={rate:.2f} H/s", flush=True)
                continue
            if scan.returncode != 0:
                raise RuntimeError(f"native scanner failed: {scan.stderr.strip() or scan.stdout.strip()}")

            nonce, block_hash, attempts = parse_scan_result(scan.stdout)
            header[76:80] = struct.pack("<I", nonce)
            block_hex = (bytes(header) + block_tail).hex()

            submit = rpc.call("submitblock", block_hex)
            if submit not in (None, "", "duplicate"):
                print(f"crakminer-native rejected hash={block_hash} reason={submit}", file=sys.stderr, flush=True)
                continue

            try:
                info = rpc.call("getblockheader", block_hash)
            except RuntimeError:
                info = None
            confirmations = int(info.get("confirmations", 0)) if isinstance(info, dict) else 0
            if confirmations <= 0:
                print(f"crakminer-native stale_or_side hash={block_hash}", file=sys.stderr, flush=True)
                continue

            accepted += 1
            rate = attempts / elapsed
            print(
                f"crakminer-native accepted={accepted} nonce={nonce} confirmations={confirmations} "
                f"hash={block_hash} attempts={attempts} rate={rate:.2f} H/s",
                flush=True,
            )
    except KeyboardInterrupt:
        print("crakminer-native stopped", file=sys.stderr)
        return 130

    print(f"crakminer-native complete accepted={accepted}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"crakminer-native: {exc}", file=sys.stderr)
        raise SystemExit(1)
