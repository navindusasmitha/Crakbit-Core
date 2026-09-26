#!/usr/bin/env python3
"""Materialize pinned Bitcoin Core with Crakbit yespower and network identity.

CRAK-004 vendors/builds pinned yespower. CRAK-005 changes CBlockHeader::GetHash()
to yespower over the canonical 80-byte header. CRAK-006 separates Crakbit
regtest/testnet4 from Bitcoin with unique magic, ports, address namespaces and
custom zero-reward genesis candidates. Mainnet, Bitcoin testnet3 and signet are
explicitly disabled until their Crakbit parameters are reviewed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".work"
LOCK = ROOT / "SOURCE_LOCK.json"
CONSENSUS = ROOT / "consensus" / "params.json"
BTC = WORK / "bitcoin"
YESPOWER = WORK / "yespower"
OUT = WORK / "crakbit"
VECTOR_PROBE = ROOT / "tests" / "yespower_vector.c"
HEADER_PROBE = ROOT / "tests" / "block_hash_vector.cpp"
GENESIS_PROBE = ROOT / "tests" / "genesis_probe.cpp"

YESPOWER_FILES = (
    "yespower-opt.c",
    "yespower-platform.c",
    "yespower.h",
    "sha256.c",
    "sha256.h",
    "sysendian.h",
    "insecure_memzero.h",
    "README",
)


def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def head(repo: Path) -> str:
    return run("git", "rev-parse", "HEAD", cwd=repo)


def require_pinned(repo: Path, expected: str, label: str) -> None:
    if not (repo / ".git").exists():
        raise SystemExit(f"missing {label} checkout at {repo}; run scripts/bootstrap.sh")
    actual = head(repo)
    if actual != expected:
        raise SystemExit(f"{label} pin mismatch: expected {expected}, got {actual}")


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one materializer anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def section_replace(text: str, start: str, end: str, old: str, new: str, label: str) -> str:
    start_pos = text.find(start)
    end_pos = text.find(end, start_pos + len(start))
    if start_pos < 0 or end_pos < 0:
        raise SystemExit(f"missing section for {label}")
    section = text[start_pos:end_pos]
    count = section.count(old)
    if count != 1:
        raise SystemExit(f"expected one {label} anchor, found {count}")
    section = section.replace(old, new, 1)
    return text[:start_pos] + section + text[end_pos:]


def section_regex(text: str, start: str, end: str, pattern: str, replacement: str, label: str) -> str:
    start_pos = text.find(start)
    end_pos = text.find(end, start_pos + len(start))
    if start_pos < 0 or end_pos < 0:
        raise SystemExit(f"missing section for {label}")
    section = text[start_pos:end_pos]
    section, count = re.subn(pattern, replacement, section, count=1, flags=re.DOTALL)
    if count != 1:
        raise SystemExit(f"expected one regex match for {label}, found {count}")
    return text[:start_pos] + section + text[end_pos:]


def cpp_hex_bytes(hex_string: str) -> str:
    raw = bytes.fromhex(hex_string)
    if len(raw) != 4:
        raise SystemExit("message start must be exactly four bytes")
    return "\n".join(
        f"        pchMessageStart[{i}] = 0x{byte:02x};" for i, byte in enumerate(raw)
    )


def cpp_ext_key(hex_string: str) -> str:
    raw = bytes.fromhex(hex_string)
    if len(raw) != 4:
        raise SystemExit("extended-key version must be exactly four bytes")
    return "{" + ", ".join(f"0x{byte:02X}" for byte in raw) + "}"


def apply_block_hash_patch(tree: Path) -> None:
    block_cpp = tree / "src" / "primitives" / "block.cpp"

    replace_once(
        block_cpp,
        "#include <hash.h>\n#include <tinyformat.h>",
        "#include <crypto/yespower/yespower.h>\n#include <streams.h>\n#include <tinyformat.h>",
    )
    replace_once(
        block_cpp,
        "#include <memory>\n#include <span>",
        "#include <cstdlib>\n#include <memory>\n#include <span>",
    )
    replace_once(
        block_cpp,
        """uint256 CBlockHeader::GetHash() const
{
    return (HashWriter{} << *this).GetHash();
}
""",
        """uint256 CBlockHeader::GetHash() const
{
    DataStream stream{};
    stream << *this;

    if (stream.size() != 80) {
        std::abort();
    }

    static constexpr unsigned char PERS[] = "Crakbit-Core-v0.1";
    const yespower_params_t params{
        YESPOWER_1_0,
        2048,
        8,
        reinterpret_cast<const uint8_t*>(PERS),
        sizeof(PERS) - 1,
    };

    yespower_binary_t out{};
    if (yespower_tls(
            reinterpret_cast<const uint8_t*>(stream.data()),
            stream.size(),
            &params,
            &out) != 0) {
        std::abort();
    }

    return uint256{std::span<const unsigned char>{out.uc, sizeof(out.uc)}};
}
""",
    )


def apply_network_patch(tree: Path, params: dict) -> None:
    networks = params["networks"]
    testnet = networks["testnet4"]
    regtest = networks["regtest"]

    chainparams = tree / "src" / "kernel" / "chainparams.cpp"
    text = chainparams.read_text(encoding="utf-8")
    text = text.replace("#include <span>\n#include <utility>", "#include <span>\n#include <stdexcept>\n#include <utility>", 1)

    test_start = "class CTestNet4Params : public CChainParams"
    test_end = "/**\n * Signet: test network"
    reg_start = "class CRegTestParams : public CChainParams"
    reg_end = "std::unique_ptr<const CChainParams> CChainParams::SigNet"

    text = section_replace(text, test_start, test_end,
        "        consensus.nSubsidyHalvingInterval = 210000;",
        "        consensus.nSubsidyHalvingInterval = 2100000;", "testnet subsidy")
    text = section_replace(text, test_start, test_end,
        "        consensus.powLimit = uint256{\"00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffff\"};",
        "        consensus.powLimit = uint256{\"000fffff00000000000000000000000000000000000000000000000000000000\"};",
        "testnet pow limit")
    text = section_replace(text, test_start, test_end,
        "        consensus.nPowTargetTimespan = 14 * 24 * 60 * 60; // two weeks\n        consensus.nPowTargetSpacing = 10 * 60;",
        "        // Temporary Bitcoin-style retarget window until CRAK-007 ASERT lands.\n        consensus.nPowTargetTimespan = 60 * 60;\n        consensus.nPowTargetSpacing = 60;",
        "testnet spacing")

    old_test_magic = """        pchMessageStart[0] = 0x1c;
        pchMessageStart[1] = 0x16;
        pchMessageStart[2] = 0x3f;
        pchMessageStart[3] = 0x28;
        nDefaultPort = 48333;"""
    text = section_replace(text, test_start, test_end, old_test_magic,
        cpp_hex_bytes(testnet["message_start_hex"]) + f"\n        nDefaultPort = {testnet['p2p_port']};",
        "testnet magic/port")

    old_test_genesis = """        const char* testnet4_genesis_msg = "03/May/2024 000000000000000000001ebd58c244970b3aa9d783bb001011fbe8ea8e98e00e";
        const CScript testnet4_genesis_script = CScript() << "000000000000000000000000000000000000000000000000000000000000000000"_hex << OP_CHECKSIG;
        genesis = CreateGenesisBlock(testnet4_genesis_msg,
                testnet4_genesis_script,
                1714777860,
                393743547,
                0x1d00ffff,
                1,
                50 * COIN);
        consensus.hashGenesisBlock = genesis.GetHash();
        assert(consensus.hashGenesisBlock == uint256{"00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043"});
        assert(genesis.hashMerkleRoot == uint256{"7aa0a7ae1e223414cb807e40cd57e667b718e42aaf9306db9102fe28912b7b4e"});"""
    tg = testnet["genesis"]
    test_nonce = 0 if tg["nonce"] is None else tg["nonce"]
    new_test_genesis = f"""        const char* crakbit_testnet_genesis_msg = "{tg['timestamp']}";
        const CScript crakbit_testnet_genesis_script = CScript() << OP_RETURN;
        genesis = CreateGenesisBlock(crakbit_testnet_genesis_msg,
                crakbit_testnet_genesis_script,
                {tg['time']},
                {test_nonce},
                {tg['bits']},
                {tg['version']},
                {tg['reward_coins']} * COIN);
        consensus.hashGenesisBlock = genesis.GetHash();
        // CRAK-006 discovery pass: tests/genesis_probe.cpp mines/fixes the nonce.
"""
    text = section_replace(text, test_start, test_end, old_test_genesis, new_test_genesis.rstrip(), "testnet genesis")

    old_test_seeds = """        vFixedSeeds.clear();
        vSeeds.clear();
        // nodes with support for servicebits filtering should be at the top
        vSeeds.emplace_back("seed.testnet4.bitcoin.sprovoost.nl."); // Sjors Provoost
        vSeeds.emplace_back("seed.testnet4.wiz.biz."); // Jason Maurice"""
    text = section_replace(text, test_start, test_end, old_test_seeds,
        "        vFixedSeeds.clear();\n        vSeeds.clear(); // Crakbit seeds are added only after independent testnet nodes exist.",
        "testnet seeds")

    old_test_prefixes = """        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1,111);
        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1,196);
        base58Prefixes[SECRET_KEY] =     std::vector<unsigned char>(1,239);
        base58Prefixes[EXT_PUBLIC_KEY] = {0x04, 0x35, 0x87, 0xCF};
        base58Prefixes[EXT_SECRET_KEY] = {0x04, 0x35, 0x83, 0x94};

        bech32_hrp = "tb";

        vFixedSeeds = std::vector<uint8_t>(std::begin(chainparams_seed_testnet4), std::end(chainparams_seed_testnet4));"""
    tb = testnet["base58"]
    new_test_prefixes = f"""        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1,{tb['pubkey_address']});
        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1,{tb['script_address']});
        base58Prefixes[SECRET_KEY] =     std::vector<unsigned char>(1,{tb['secret_key']});
        base58Prefixes[EXT_PUBLIC_KEY] = {cpp_ext_key(tb['ext_public_key_hex'])};
        base58Prefixes[EXT_SECRET_KEY] = {cpp_ext_key(tb['ext_secret_key_hex'])};

        bech32_hrp = "{testnet['bech32_hrp']}";

        vFixedSeeds.clear();"""
    text = section_replace(text, test_start, test_end, old_test_prefixes, new_test_prefixes, "testnet address prefixes")
    text = section_regex(text, test_start, test_end,
        r"        m_assumeutxo_data = \{\n.*?        chainTxData = ChainTxData\{\n.*?        \};\n\n        // Generated by headerssync-params.py",
        "        m_assumeutxo_data.clear();\n        chainTxData = ChainTxData{0, 0, 0};\n\n        // Generated by headerssync-params.py",
        "testnet stale snapshot data")

    text = section_replace(text, reg_start, reg_end,
        "        consensus.nSubsidyHalvingInterval = 150;",
        "        consensus.nSubsidyHalvingInterval = 2100000;", "regtest subsidy")
    text = section_replace(text, reg_start, reg_end,
        "        consensus.nPowTargetSpacing = 10 * 60;",
        "        consensus.nPowTargetSpacing = 60;", "regtest spacing")
    old_reg_magic = """        pchMessageStart[0] = 0xfa;
        pchMessageStart[1] = 0xbf;
        pchMessageStart[2] = 0xb5;
        pchMessageStart[3] = 0xda;
        nDefaultPort = 18444;"""
    text = section_replace(text, reg_start, reg_end, old_reg_magic,
        cpp_hex_bytes(regtest["message_start_hex"]) + f"\n        nDefaultPort = {regtest['p2p_port']};",
        "regtest magic/port")

    old_reg_genesis = """        genesis = CreateGenesisBlock(1296688602, 2, 0x207fffff, 1, 50 * COIN);
        consensus.hashGenesisBlock = genesis.GetHash();
        assert(consensus.hashGenesisBlock == uint256{"0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206"});
        assert(genesis.hashMerkleRoot == uint256{"4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"});"""
    rg = regtest["genesis"]
    reg_nonce = 0 if rg["nonce"] is None else rg["nonce"]
    new_reg_genesis = f"""        const char* crakbit_regtest_genesis_msg = "{rg['timestamp']}";
        const CScript crakbit_regtest_genesis_script = CScript() << OP_RETURN;
        genesis = CreateGenesisBlock(crakbit_regtest_genesis_msg,
                crakbit_regtest_genesis_script,
                {rg['time']},
                {reg_nonce},
                {rg['bits']},
                {rg['version']},
                {rg['reward_coins']} * COIN);
        consensus.hashGenesisBlock = genesis.GetHash();
        // CRAK-006 discovery pass: tests/genesis_probe.cpp mines/fixes the nonce."""
    text = section_replace(text, reg_start, reg_end, old_reg_genesis, new_reg_genesis, "regtest genesis")

    old_reg_seeds = """        vFixedSeeds.clear(); //!< Regtest mode doesn't have any fixed seeds.
        vSeeds.clear();
        vSeeds.emplace_back("dummySeed.invalid.");"""
    text = section_replace(text, reg_start, reg_end, old_reg_seeds,
        "        vFixedSeeds.clear();\n        vSeeds.clear();",
        "regtest seeds")
    text = section_regex(text, reg_start, reg_end,
        r"        m_assumeutxo_data = \{\n.*?        chainTxData = ChainTxData\{\n.*?        \};\n\n        base58Prefixes",
        "        m_assumeutxo_data.clear();\n        chainTxData = ChainTxData{0, 0, 0};\n\n        base58Prefixes",
        "regtest stale snapshot data")
    old_reg_prefixes = """        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1,111);
        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1,196);
        base58Prefixes[SECRET_KEY] =     std::vector<unsigned char>(1,239);
        base58Prefixes[EXT_PUBLIC_KEY] = {0x04, 0x35, 0x87, 0xCF};
        base58Prefixes[EXT_SECRET_KEY] = {0x04, 0x35, 0x83, 0x94};

        bech32_hrp = "bcrt";"""
    rb = regtest["base58"]
    new_reg_prefixes = f"""        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1,{rb['pubkey_address']});
        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1,{rb['script_address']});
        base58Prefixes[SECRET_KEY] =     std::vector<unsigned char>(1,{rb['secret_key']});
        base58Prefixes[EXT_PUBLIC_KEY] = {cpp_ext_key(rb['ext_public_key_hex'])};
        base58Prefixes[EXT_SECRET_KEY] = {cpp_ext_key(rb['ext_secret_key_hex'])};

        bech32_hrp = "{regtest['bech32_hrp']}";"""
    text = section_replace(text, reg_start, reg_end, old_reg_prefixes, new_reg_prefixes, "regtest address prefixes")

    text = text.replace(
        """std::unique_ptr<const CChainParams> CChainParams::SigNet(const SigNetOptions& options)
{
    return std::make_unique<const SigNetParams>(options);
}""",
        """std::unique_ptr<const CChainParams> CChainParams::SigNet(const SigNetOptions&)
{
    throw std::runtime_error("Crakbit signet is disabled in v0.1");
}""", 1)
    text = text.replace(
        """std::unique_ptr<const CChainParams> CChainParams::Main()
{
    return std::make_unique<const CMainParams>();
}""",
        """std::unique_ptr<const CChainParams> CChainParams::Main()
{
    throw std::runtime_error("Crakbit mainnet is disabled until testnet launch gates pass");
}""", 1)
    text = text.replace(
        """std::unique_ptr<const CChainParams> CChainParams::TestNet()
{
    return std::make_unique<const CTestNetParams>();
}""",
        """std::unique_ptr<const CChainParams> CChainParams::TestNet()
{
    throw std::runtime_error("Bitcoin testnet3 compatibility is disabled in Crakbit Core");
}""", 1)

    network_magic_pattern = r"std::optional<ChainType> GetNetworkForMagic\(const MessageStartChars& message\)\n\{.*?\n\}"
    network_magic_replacement = """std::optional<ChainType> GetNetworkForMagic(const MessageStartChars& message)
{
    const auto testnet4_msg = CChainParams::TestNet4()->MessageStart();
    const auto regtest_msg = CChainParams::RegTest({})->MessageStart();

    if (std::ranges::equal(message, testnet4_msg)) {
        return ChainType::TESTNET4;
    }
    if (std::ranges::equal(message, regtest_msg)) {
        return ChainType::REGTEST;
    }
    return std::nullopt;
}"""
    text, count = re.subn(network_magic_pattern, network_magic_replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise SystemExit("failed to replace GetNetworkForMagic")
    chainparams.write_text(text, encoding="utf-8")

    public_chainparams = tree / "src" / "chainparams.cpp"
    ptext = public_chainparams.read_text(encoding="utf-8")
    ptext = ptext.replace(
        """    case ChainType::MAIN:
        return CChainParams::Main();""",
        """    case ChainType::MAIN:
        throw std::runtime_error("Crakbit mainnet is disabled until testnet launch gates pass");""", 1)
    ptext = ptext.replace(
        """    case ChainType::TESTNET:
        return CChainParams::TestNet();""",
        """    case ChainType::TESTNET:
        throw std::runtime_error("Bitcoin testnet3 compatibility is disabled in Crakbit Core");""", 1)
    signet_pattern = r"    case ChainType::SIGNET: \{\n        auto opts = CChainParams::SigNetOptions\{\};\n        ReadSigNetArgs\(args, opts\);\n        return CChainParams::SigNet\(opts\);\n    \}"
    ptext, count = re.subn(signet_pattern,
        "    case ChainType::SIGNET:\n        throw std::runtime_error(\"Crakbit signet is disabled in v0.1\");",
        ptext, count=1)
    if count != 1:
        raise SystemExit("failed to disable signet selection")
    public_chainparams.write_text(ptext, encoding="utf-8")

    baseparams = tree / "src" / "chainparamsbase.cpp"
    btext = baseparams.read_text(encoding="utf-8")
    btext = btext.replace(
        "return std::make_unique<CBaseChainParams>(\"testnet4\", 48332);",
        f"return std::make_unique<CBaseChainParams>(\"testnet4\", {testnet['rpc_port']});", 1)
    btext = btext.replace(
        "return std::make_unique<CBaseChainParams>(\"regtest\", 18443);",
        f"return std::make_unique<CBaseChainParams>(\"regtest\", {regtest['rpc_port']});", 1)
    baseparams.write_text(btext, encoding="utf-8")


def main() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    consensus_params = json.loads(CONSENSUS.read_text(encoding="utf-8"))
    btc_lock = lock["upstreams"]["bitcoin_core"]
    yes_lock = lock["upstreams"]["yespower"]

    require_pinned(BTC, btc_lock["commit_sha"], "Bitcoin Core")
    require_pinned(YESPOWER, yes_lock["commit_sha"], "yespower")
    for probe in (VECTOR_PROBE, HEADER_PROBE, GENESIS_PROBE):
        if not probe.is_file():
            raise SystemExit(f"missing Crakbit vector probe: {probe}")

    if OUT.exists():
        shutil.rmtree(OUT)
    run("git", "worktree", "prune", cwd=BTC)
    run("git", "worktree", "add", "--force", "--detach", str(OUT), btc_lock["commit_sha"], cwd=BTC)
    if head(OUT) != btc_lock["commit_sha"]:
        raise SystemExit("materialized Bitcoin Core HEAD does not match SOURCE_LOCK.json")

    vendor = OUT / "src" / "crypto" / "yespower"
    vendor.mkdir(parents=True, exist_ok=True)
    for name in YESPOWER_FILES:
        src = YESPOWER / name
        if not src.is_file():
            raise SystemExit(f"required yespower source is missing: {src}")
        shutil.copy2(src, vendor / name)
    shutil.copy2(VECTOR_PROBE, vendor / "crakbit-vector.c")
    shutil.copy2(HEADER_PROBE, vendor / "crakbit-header-vector.cpp")
    shutil.copy2(GENESIS_PROBE, vendor / "crakbit-genesis-probe.cpp")

    yespower_cmake = "\n".join([
        "# Crakbit Core: pinned Openwall yespower build target.",
        "add_library(crakbit_yespower STATIC EXCLUDE_FROM_ALL",
        "  yespower-opt.c",
        "  sha256.c",
        ")",
        "target_include_directories(crakbit_yespower PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})",
        "target_link_libraries(crakbit_yespower PRIVATE core_interface)",
        "set_target_properties(crakbit_yespower PROPERTIES C_STANDARD 99 C_STANDARD_REQUIRED YES)",
        "",
        "add_executable(crakbit_yespower_vector EXCLUDE_FROM_ALL crakbit-vector.c)",
        "target_link_libraries(crakbit_yespower_vector PRIVATE crakbit_yespower)",
        "set_target_properties(crakbit_yespower_vector PROPERTIES C_STANDARD 99 C_STANDARD_REQUIRED YES)",
        "",
    ])
    (vendor / "CMakeLists.txt").write_text(yespower_cmake, encoding="utf-8")

    src_cmake = OUT / "src" / "CMakeLists.txt"
    replace_once(src_cmake,
        "add_subdirectory(crypto)\nadd_subdirectory(util)",
        "add_subdirectory(crypto)\nadd_subdirectory(crypto/yespower)\nadd_subdirectory(util)")
    replace_once(src_cmake,
        "    bitcoin_crypto\n    secp256k1\n",
        "    bitcoin_crypto\n    crakbit_yespower\n    secp256k1\n")
    replace_once(src_cmake,
        """target_link_libraries(bitcoin_consensus
  PRIVATE
    core_interface
    bitcoin_crypto
    crakbit_yespower
    secp256k1
)
""",
        """target_link_libraries(bitcoin_consensus
  PRIVATE
    core_interface
    bitcoin_crypto
    crakbit_yespower
    secp256k1
)

add_executable(crakbit_header_hash_vector EXCLUDE_FROM_ALL
  crypto/yespower/crakbit-header-vector.cpp
)
target_link_libraries(crakbit_header_hash_vector PRIVATE bitcoin_consensus)
""")
    replace_once(src_cmake,
        """target_link_libraries(bitcoin_common
  PRIVATE
    core_interface
    bitcoin_consensus
    bitcoin_util
    univalue
    secp256k1
    Boost::headers
    $<TARGET_NAME_IF_EXISTS:USDT::headers>
    $<$<PLATFORM_ID:Windows>:ws2_32>
)
""",
        """target_link_libraries(bitcoin_common
  PRIVATE
    core_interface
    bitcoin_consensus
    bitcoin_util
    univalue
    secp256k1
    Boost::headers
    $<TARGET_NAME_IF_EXISTS:USDT::headers>
    $<$<PLATFORM_ID:Windows>:ws2_32>
)

add_executable(crakbit_genesis_probe EXCLUDE_FROM_ALL
  crypto/yespower/crakbit-genesis-probe.cpp
)
target_link_libraries(crakbit_genesis_probe PRIVATE bitcoin_common)
""")

    apply_block_hash_patch(OUT)
    apply_network_patch(OUT, consensus_params)

    manifest = WORK / "materialized-source.txt"
    manifest.write_text("\n".join([
        "project=Crakbit Core",
        "stage=CRAK-006-network-genesis-discovery",
        f"bitcoin_core_commit={btc_lock['commit_sha']}",
        f"yespower_commit={yes_lock['commit_sha']}",
        "block_header_serialized_bytes=80",
        "block_identity_hash=yespower",
        "testnet4_magic=" + consensus_params["networks"]["testnet4"]["message_start_hex"],
        "regtest_magic=" + consensus_params["networks"]["regtest"]["message_start_hex"],
        "bitcoin_mainnet_enabled=false",
        "bitcoin_testnet3_enabled=false",
        "signet_enabled=false",
        "mainnet_enabled=false",
        "",
    ]), encoding="utf-8")

    print(f"materialized: {OUT}")
    print(f"bitcoin:      {btc_lock['commit_sha']}")
    print(f"yespower:     {yes_lock['commit_sha']}")
    print("stage:        CRAK-006 Crakbit testnet/regtest identity + genesis discovery")


if __name__ == "__main__":
    main()
