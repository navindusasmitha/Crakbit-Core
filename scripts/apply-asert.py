#!/usr/bin/env python3
"""Apply CRAK-007 ASERT to the CRAK-006 locked materialized tree."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / ".work" / "crakbit"
MANIFEST = ROOT / ".work" / "materialized-source.txt"
PARAMS = json.loads((ROOT / "consensus" / "params.json").read_text(encoding="utf-8"))
CRAKBIT_SRC = ROOT / "src" / "crakbit"
ASERT_PROBE = ROOT / "tests" / "asert_vector.cpp"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one CRAK-007 anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def section_replace(path: Path, start: str, end: str, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    start_pos = text.find(start)
    end_pos = text.find(end, start_pos + len(start))
    if start_pos < 0 or end_pos < 0:
        raise SystemExit(f"missing CRAK-007 section: {label}")
    section = text[start_pos:end_pos]
    if section.count(old) != 1:
        raise SystemExit(f"expected one CRAK-007 {label} anchor, found {section.count(old)}")
    section = section.replace(old, new, 1)
    path.write_text(text[:start_pos] + section + text[end_pos:], encoding="utf-8")


def main() -> None:
    if not TREE.is_dir():
        raise SystemExit("missing CRAK-006 materialized tree; run scripts/materialize-locked.sh")
    if not MANIFEST.is_file():
        raise SystemExit("missing materialized-source manifest")

    half_life = int(PARAMS["difficulty"]["half_life_seconds"])
    spacing = int(PARAMS["proof_of_work"]["target_spacing_seconds"])
    if half_life != 7200 or spacing != 60:
        raise SystemExit("CRAK-007 profile must remain 60-second spacing / 7200-second half-life")

    dest = TREE / "src" / "crakbit"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("asert.h", "asert.cpp"):
        source = CRAKBIT_SRC / name
        if not source.is_file():
            raise SystemExit(f"missing CRAK-007 source: {source}")
        shutil.copy2(source, dest / name)
    if not ASERT_PROBE.is_file():
        raise SystemExit(f"missing CRAK-007 probe: {ASERT_PROBE}")
    shutil.copy2(ASERT_PROBE, dest / "asert-vector.cpp")

    # Crakbit's easy CPU-test powLimit does not satisfy the reference ASERT
    # implementation's 32-leading-zero headroom assumption. Instantiate the
    # existing Bitcoin base_uint template at 512 bits for exact intermediates.
    arith_cpp = TREE / "src" / "arith_uint256.cpp"
    replace_once(
        arith_cpp,
        "// Explicit instantiations for base_uint<256>\ntemplate class base_uint<256>;",
        "// Explicit instantiations used by Bitcoin and Crakbit ASERT.\n"
        "template class base_uint<256>;\n"
        "template class base_uint<512>;",
    )

    consensus_h = TREE / "src" / "consensus" / "params.h"
    replace_once(
        consensus_h,
        "    bool fPowNoRetargeting;\n    int64_t nPowTargetSpacing;",
        "    bool fPowNoRetargeting;\n"
        "    bool fPowUseASERT{false};\n"
        "    int64_t nASERTHalfLife{0};\n"
        "    int64_t nPowTargetSpacing;",
    )

    pow_cpp = TREE / "src" / "pow.cpp"
    replace_once(
        pow_cpp,
        "#include <arith_uint256.h>\n#include <chain.h>",
        "#include <arith_uint256.h>\n#include <crakbit/asert.h>\n#include <chain.h>",
    )
    replace_once(
        pow_cpp,
        """    assert(pindexLast != nullptr);
    unsigned int nProofOfWorkLimit = UintToArith256(params.powLimit).GetCompact();
""",
        """    assert(pindexLast != nullptr);

    if (params.fPowNoRetargeting) {
        return pindexLast->nBits;
    }
    if (params.fPowUseASERT) {
        return crakbit::GetNextASERTWorkRequired(pindexLast, params);
    }

    unsigned int nProofOfWorkLimit = UintToArith256(params.powLimit).GetCompact();
""",
    )
    replace_once(
        pow_cpp,
        """bool PermittedDifficultyTransition(const Consensus::Params& params, int64_t height, uint32_t old_nbits, uint32_t new_nbits)
{
    if (params.fPowAllowMinDifficultyBlocks) return true;
""",
        """bool PermittedDifficultyTransition(const Consensus::Params& params, int64_t height, uint32_t old_nbits, uint32_t new_nbits)
{
    // Header sync does not have the timestamp/anchor context needed to
    // reproduce absolute ASERT here. Full block-header validation checks the
    // exact value through GetNextWorkRequired(). Mainnet remains disabled.
    if (params.fPowUseASERT) return true;
    if (params.fPowAllowMinDifficultyBlocks) return true;
""",
    )

    chainparams = TREE / "src" / "kernel" / "chainparams.cpp"
    test_start = "class CTestNet4Params : public CChainParams"
    test_end = "/**\n * Signet: test network"
    reg_start = "class CRegTestParams : public CChainParams"
    reg_end = "std::unique_ptr<const CChainParams> CChainParams::SigNet"

    section_replace(chainparams, test_start, test_end,
                    "        consensus.fPowAllowMinDifficultyBlocks = true;",
                    "        consensus.fPowAllowMinDifficultyBlocks = false;",
                    "testnet min-difficulty")
    section_replace(chainparams, test_start, test_end,
                    "        consensus.enforce_BIP94 = true;",
                    "        consensus.enforce_BIP94 = false;",
                    "testnet BIP94 legacy retarget")
    section_replace(
        chainparams,
        test_start,
        test_end,
        "        consensus.fPowNoRetargeting = false;",
        "        consensus.fPowNoRetargeting = false;\n"
        "        consensus.fPowUseASERT = true;\n"
        f"        consensus.nASERTHalfLife = {half_life};",
        "testnet ASERT activation",
    )
    section_replace(
        chainparams,
        reg_start,
        reg_end,
        "        consensus.fPowNoRetargeting = true;",
        "        consensus.fPowNoRetargeting = true;\n"
        "        consensus.fPowUseASERT = false;\n"
        f"        consensus.nASERTHalfLife = {half_life};",
        "regtest ASERT bypass",
    )

    cmake = TREE / "src" / "CMakeLists.txt"
    replace_once(
        cmake,
        "  pow.cpp\n  protocol.cpp",
        "  pow.cpp\n  crakbit/asert.cpp\n  protocol.cpp",
    )
    replace_once(
        cmake,
        """add_executable(crakbit_genesis_probe EXCLUDE_FROM_ALL
  crypto/yespower/crakbit-genesis-probe.cpp
)
target_link_libraries(crakbit_genesis_probe PRIVATE bitcoin_common)
""",
        """add_executable(crakbit_genesis_probe EXCLUDE_FROM_ALL
  crypto/yespower/crakbit-genesis-probe.cpp
)
target_link_libraries(crakbit_genesis_probe PRIVATE bitcoin_common)

add_executable(crakbit_asert_vector EXCLUDE_FROM_ALL
  crakbit/asert-vector.cpp
)
target_link_libraries(crakbit_asert_vector PRIVATE bitcoin_common)
""",
    )

    manifest = MANIFEST.read_text(encoding="utf-8")
    if "stage=CRAK-006-network-genesis-locked" not in manifest:
        raise SystemExit("CRAK-007 requires a CRAK-006 genesis-locked manifest")
    manifest = manifest.replace(
        "stage=CRAK-006-network-genesis-locked",
        "stage=CRAK-007-asert-locked",
        1,
    )
    manifest += (
        "difficulty_algorithm=ASERT\n"
        f"difficulty_target_spacing_seconds={spacing}\n"
        f"difficulty_half_life_seconds={half_life}\n"
        "difficulty_anchor=genesis-conceptual-parent-minus-one-spacing\n"
        "testnet_min_difficulty=false\n"
        "regtest_no_retarget=true\n"
    )
    MANIFEST.write_text(manifest, encoding="utf-8")

    print("CRAK-007 ASERT applied to materialized source")


if __name__ == "__main__":
    main()
