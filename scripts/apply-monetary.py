#!/usr/bin/env python3
"""Apply CRAK-008 monetary consensus to the CRAK-007 materialized tree."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / ".work" / "crakbit"
MANIFEST = ROOT / ".work" / "materialized-source.txt"
PARAMS = json.loads((ROOT / "consensus" / "params.json").read_text(encoding="utf-8"))
VECTORS = json.loads((ROOT / "tests" / "subsidy_vectors.json").read_text(encoding="utf-8"))
CRAKBIT_SRC = ROOT / "src" / "crakbit"
SUBSIDY_PROBE = ROOT / "tests" / "subsidy_vector.cpp"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one CRAK-008 anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def require_in_section(path: Path, start: str, end: str, needle: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    start_pos = text.find(start)
    end_pos = text.find(end, start_pos + len(start))
    if start_pos < 0 or end_pos < 0:
        raise SystemExit(f"missing CRAK-008 section: {label}")
    if needle not in text[start_pos:end_pos]:
        raise SystemExit(f"missing CRAK-008 {label} lock: {needle}")


def main() -> None:
    if not TREE.is_dir() or not MANIFEST.is_file():
        raise SystemExit("missing CRAK-007 materialized tree; run scripts/materialize-locked.sh")

    money = PARAMS["money"]
    profile = VECTORS["profile"]
    if money["initial_subsidy_coins"] != 5:
        raise SystemExit("CRAK-008 initial subsidy must be 5 CRAK")
    if money["halving_interval_blocks"] != 2_100_000:
        raise SystemExit("CRAK-008 halving interval must be 2,100,000 blocks")
    if money["coinbase_maturity_blocks"] != 100:
        raise SystemExit("CRAK-008 coinbase maturity must remain 100 blocks")
    if money["premine_coins"] != 0:
        raise SystemExit("CRAK-008 premine must remain zero")

    expected_profile = {
        "initial_subsidy_sats": 500_000_000,
        "halving_interval_blocks": 2_100_000,
        "coinbase_maturity_blocks": 100,
        "premine_sats": 0,
        "integer_rounded_max_subsidy_sats": 2_099_999_972_700_000,
    }
    if profile != expected_profile:
        raise SystemExit("CRAK-008 frozen subsidy profile mismatch")

    dest = TREE / "src" / "crakbit"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("subsidy.h", "subsidy.cpp"):
        source = CRAKBIT_SRC / name
        if not source.is_file():
            raise SystemExit(f"missing CRAK-008 source: {source}")
        shutil.copy2(source, dest / name)
    if not SUBSIDY_PROBE.is_file():
        raise SystemExit(f"missing CRAK-008 probe: {SUBSIDY_PROBE}")
    shutil.copy2(SUBSIDY_PROBE, dest / "subsidy-vector.cpp")

    validation = TREE / "src" / "validation.cpp"
    replace_once(
        validation,
        "#include <consensus/validation.h>\n#include <cuckoocache.h>",
        "#include <consensus/validation.h>\n#include <crakbit/subsidy.h>\n#include <cuckoocache.h>",
    )
    replace_once(
        validation,
        """CAmount GetBlockSubsidy(int nHeight, const Consensus::Params& consensusParams)
{
    int halvings = nHeight / consensusParams.nSubsidyHalvingInterval;
    // Force block reward to zero when right shift is undefined.
    if (halvings >= 64)
        return 0;

    CAmount nSubsidy = 50 * COIN;
    // Subsidy is cut in half every 210,000 blocks which will occur approximately every 4 years.
    nSubsidy >>= halvings;
    return nSubsidy;
}
""",
        """CAmount GetBlockSubsidy(int nHeight, const Consensus::Params& consensusParams)
{
    return crakbit::CalculateBlockSubsidy(nHeight, consensusParams.nSubsidyHalvingInterval);
}
""",
    )

    consensus_h = TREE / "src" / "consensus" / "consensus.h"
    consensus_text = consensus_h.read_text(encoding="utf-8")
    if "static const int COINBASE_MATURITY = 100;" not in consensus_text:
        raise SystemExit("Bitcoin Core coinbase maturity is no longer 100; CRAK-008 review required")

    chainparams = TREE / "src" / "kernel" / "chainparams.cpp"
    require_in_section(
        chainparams,
        "class CTestNet4Params : public CChainParams",
        "/**\n * Signet: test network",
        "consensus.nSubsidyHalvingInterval = 2100000;",
        "testnet halving interval",
    )
    require_in_section(
        chainparams,
        "class CRegTestParams : public CChainParams",
        "std::unique_ptr<const CChainParams> CChainParams::SigNet",
        "consensus.nSubsidyHalvingInterval = 2100000;",
        "regtest halving interval",
    )

    cmake = TREE / "src" / "CMakeLists.txt"
    replace_once(
        cmake,
        "  crakbit/asert.cpp\n  protocol.cpp",
        "  crakbit/asert.cpp\n  crakbit/subsidy.cpp\n  protocol.cpp",
    )
    replace_once(
        cmake,
        """add_executable(crakbit_asert_vector EXCLUDE_FROM_ALL
  crakbit/asert-vector.cpp
)
target_link_libraries(crakbit_asert_vector PRIVATE bitcoin_common)
""",
        """add_executable(crakbit_asert_vector EXCLUDE_FROM_ALL
  crakbit/asert-vector.cpp
)
target_link_libraries(crakbit_asert_vector PRIVATE bitcoin_common)

add_executable(crakbit_subsidy_vector EXCLUDE_FROM_ALL
  crakbit/subsidy-vector.cpp
)
target_link_libraries(crakbit_subsidy_vector PRIVATE bitcoin_common)
""",
    )

    manifest = MANIFEST.read_text(encoding="utf-8")
    if "stage=CRAK-007-asert-locked" not in manifest:
        raise SystemExit("CRAK-008 requires a CRAK-007 ASERT-locked manifest")
    manifest = manifest.replace(
        "stage=CRAK-007-asert-locked",
        "stage=CRAK-008-monetary-consensus-locked",
        1,
    )
    manifest += (
        "initial_subsidy_sats=500000000\n"
        "halving_interval_blocks=2100000\n"
        "coinbase_maturity_blocks=100\n"
        "premine_sats=0\n"
        "integer_rounded_max_subsidy_sats=2099999972700000\n"
    )
    MANIFEST.write_text(manifest, encoding="utf-8")

    print("CRAK-008 monetary consensus applied to materialized source")


if __name__ == "__main__":
    main()
