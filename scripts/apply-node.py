#!/usr/bin/env python3
"""Apply CRAK-009 full-node/CLI integration to the CRAK-008 materialized tree."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / ".work" / "crakbit"
MANIFEST = ROOT / ".work" / "materialized-source.txt"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one CRAK-009 anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    if not TREE.is_dir() or not MANIFEST.is_file():
        raise SystemExit("missing CRAK-008 materialized tree; run scripts/materialize-locked.sh")

    manifest = MANIFEST.read_text(encoding="utf-8")
    if "stage=CRAK-008-monetary-consensus-locked" not in manifest:
        raise SystemExit("CRAK-009 requires a CRAK-008 monetary-consensus-locked manifest")

    # Preserve upstream CMake target names so dependency wiring stays boring and
    # reviewable, but expose Crakbit-native executable names to operators.
    cmake = TREE / "src" / "CMakeLists.txt"
    replace_once(
        cmake,
        """  target_link_libraries(bitcoind
    core_interface
    bitcoin_node
    $<TARGET_NAME_IF_EXISTS:bitcoin_wallet>
  )
  install_binary_component(bitcoind HAS_MANPAGE)
""",
        """  target_link_libraries(bitcoind
    core_interface
    bitcoin_node
    $<TARGET_NAME_IF_EXISTS:bitcoin_wallet>
  )
  set_target_properties(bitcoind PROPERTIES OUTPUT_NAME crakbitd)
  install_binary_component(bitcoind HAS_MANPAGE)
""",
    )
    replace_once(
        cmake,
        """  target_link_libraries(bitcoin-cli
    core_interface
    bitcoin_cli
    bitcoin_common
    bitcoin_util
    libevent::core
    libevent::extra
  )
  install_binary_component(bitcoin-cli HAS_MANPAGE)
""",
        """  target_link_libraries(bitcoin-cli
    core_interface
    bitcoin_cli
    bitcoin_common
    bitcoin_util
    libevent::core
    libevent::extra
  )
  set_target_properties(bitcoin-cli PROPERTIES OUTPUT_NAME crakbit-cli)
  install_binary_component(bitcoin-cli HAS_MANPAGE)
""",
    )

    # The upstream mining RPC already increments the 32-bit nonce and calls
    # CBlock::GetHash()/CheckProofOfWork(). CRAK-005 makes GetHash() yespower,
    # so this is the consensus-correct single-thread CPU mining path.
    mining_rpc = TREE / "src" / "rpc" / "mining.cpp"
    mining_text = mining_rpc.read_text(encoding="utf-8")
    required = (
        "while (max_tries > 0 && block.nNonce < std::numeric_limits<uint32_t>::max()",
        "CheckProofOfWork(block.GetHash(), block.nBits, chainman.GetConsensus())",
        "static RPCHelpMan generatetodescriptor()",
    )
    for needle in required:
        if needle not in mining_text:
            raise SystemExit(f"CRAK-009 mining RPC anchor missing: {needle}")

    manifest = manifest.replace(
        "stage=CRAK-008-monetary-consensus-locked",
        "stage=CRAK-009-node-integration-ready",
        1,
    )
    manifest += (
        "daemon_binary=crakbitd\n"
        "cli_binary=crakbit-cli\n"
        "cpu_mining_rpc=generatetodescriptor\n"
        "cpu_mining_hash=yespower-block-header\n"
        "node_smoke_nodes=3\n"
        "reorg_smoke_required=true\n"
        "invalid_block_smoke_required=true\n"
    )
    MANIFEST.write_text(manifest, encoding="utf-8")

    print("CRAK-009 full-node integration applied to materialized source")


if __name__ == "__main__":
    main()
